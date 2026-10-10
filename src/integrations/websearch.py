from __future__ import annotations

import threading
import time
import uuid
from ..utility.message_chunk import get_message_chunks
from ..extensions import NewelleExtension
from ..tools import ToolResult, Tool, Command
from gi.repository import GLib
import os
import json


class WebsearchIntegration(NewelleExtension):
    id = "websearch"
    name = "Websearch"

    def __init__(self, pip_path, extension_path, settings):
        super().__init__(pip_path, extension_path, settings)
        self.widgets = {}
        self.load_widet_cache()
        self.tool_uuid = ""
        self._meo_trace_lock = threading.Lock()
        self._meo_search_traces: dict[int, list[dict]] = {}

    def _meo_provider_label(self) -> str:
        handler = getattr(self, "websearch", None)
        key = getattr(handler, "key", "")
        if isinstance(key, str) and key:
            return key[:256]
        return type(handler).__name__[:256] if handler is not None else "websearch"

    def _start_meo_trace(self, query: str, chat_id: int | None, only_links: bool, max_results: int) -> dict | None:
        if not isinstance(chat_id, int) or isinstance(chat_id, bool):
            return None
        trace = {
            "trace_id": "search:" + uuid.uuid4().hex[:16],
            "kind": "web",
            "query": str(query)[:8192],
            "provider": self._meo_provider_label(),
            "started_monotonic": time.monotonic(),
            "duration_ms": None,
            "result_count": None,
            "sources": [],
            "filters": {
                "only_links": "true" if only_links else "false",
                "max_results": str(max_results),
            },
            "completed": False,
        }
        with self._meo_trace_lock:
            bucket = self._meo_search_traces.setdefault(chat_id, [])
            bucket.append(trace)
            if len(bucket) > 32:
                del bucket[:-32]
        return trace

    def _finish_meo_trace(self, trace: dict | None, sources: list[dict], error: str = "") -> None:
        if trace is None:
            return
        normalized = []
        for index, source in enumerate(sources[:256]):
            uri = str(source.get("uri", ""))[:8192] if isinstance(source, dict) else str(source)[:8192]
            title = str(source.get("title", "") or uri or f"Source {index + 1}")[:1024] if isinstance(source, dict) else (uri or f"Source {index + 1}")[:1024]
            normalized.append({"title": title, "uri": uri})
        trace["sources"] = normalized
        trace["result_count"] = len(normalized)
        trace["duration_ms"] = round((time.monotonic() - trace["started_monotonic"]) * 1000, 3)
        trace["completed"] = True
        if error:
            trace["error"] = str(error)[:1024]

    def consume_meo_search_traces(self, chat_id: int, since_monotonic: float = 0.0) -> list[dict]:
        """Return completed native telemetry for one chat/request window.

        This compatibility queue is bounded and contains only structured search
        facts. It is consumed by Meo AgentService rather than reconstructed from
        model prose or legacy GTK widgets.
        """
        if not isinstance(chat_id, int) or isinstance(chat_id, bool):
            return []
        with self._meo_trace_lock:
            bucket = self._meo_search_traces.get(chat_id, [])
            selected = [
                item for item in bucket
                if item.get("completed") is True
                and float(item.get("started_monotonic", 0.0)) >= float(since_monotonic)
            ]
            selected_ids = {id(item) for item in selected}
            remaining = [item for item in bucket if id(item) not in selected_ids]
            if remaining:
                self._meo_search_traces[chat_id] = remaining[-32:]
            else:
                self._meo_search_traces.pop(chat_id, None)
            return [dict(item) for item in selected]

    def search(
        self,
        query: str,
        tool_uuid: str = None,
        only_links: bool = False,
        max_results: int = 5,
        chat_id: int | None = None,
    ):
        tool_uuid = tool_uuid if tool_uuid is not None else self.ui_controller.get_current_tool_call_id()
        widget = self.get_gtk_widget(query, "", tool_uuid)
        result = ToolResult()
        result.set_widget(widget)
        result.set_display_text(_("Searching for ") + query)
        max_results = max(1, min(int(max_results), 20))
        trace = self._start_meo_trace(query, chat_id, only_links, max_results)

        def get_answer():
            try:
                out = self.get_answer(
                    query,
                    "",
                    only_links=only_links,
                    max_results=max_results,
                    trace=trace,
                )
            except Exception as error:
                self._finish_meo_trace(trace, [], error=str(error))
                out = _("Web search failed: ") + str(error)
            result.set_output(out)

        th = threading.Thread(target=get_answer, daemon=True)
        th.start()
        return result

    def restore_search(self, tool_uuid: str, query:str, only_links: bool = False, max_results: int = 5):
        widget = self.restore_gtk_widget(query, "", tool_uuid)
        return ToolResult(widget=widget)

    def get_tools(self) -> list:
        return [Tool(
            "search", "Perform a search query on the internet, you can specify the number of results to return and if you want to only return the links and titles.", self.search,title="Search", restore_func=self.restore_search, icon_name="system-search-symbolic"
            )]

    def get_commands(self) -> list:
        return [Command(
            "websearch", "Perform a search query on the internet.", self.search, restore_func=self.restore_search, icon_name="system-search-symbolic"
        )]

    def get_replace_codeblocks_langs(self) -> list:
        return ["search"]

    def provides_both_widget_and_answer(self, codeblock: str, lang: str) -> bool:
        return True

    def get_answer(
        self,
        codeblock: str,
        lang: str,
        only_links: bool = False,
        max_results: int = None,
        trace: dict | None = None,
    ) -> str | None:
        tool_uuid = self.tool_uuid
        observed_sources: list[dict] = []

        def add_observed_website(title, link, favicon):
            observed_sources.append({"title": str(title or link or ""), "uri": str(link or "")})
            self.add_website(codeblock, title, link, favicon, tool_uuid)

        if self.websearch.supports_streaming_query():
            text, sources = self.websearch.query_streaming(
                codeblock,
                add_observed_website,
                max_results=max_results,
            )
        else:
            text, sources = self.websearch.query(codeblock, max_results=max_results)
            for source in sources:
                observed_sources.append({"title": str(source), "uri": str(source)})
                self.add_website(codeblock, source, source, "", tool_uuid)
        if not observed_sources:
            for source in sources or []:
                observed_sources.append({"title": str(source), "uri": str(source)})
        self._finish_meo_trace(trace, observed_sources)
        self.finish(codeblock, text, sources, tool_uuid)
        if only_links:
            return "Here are the links for the web search result for query '" + codeblock + "':\n" + "\n".join(sources)
        return "Here is the web search result for query '"+ codeblock + "':\n" + text

    def finish(self, codeblock: str, result: str, sources, tool_uuid):
        if tool_uuid:
            tool_uuid = str(tool_uuid)
            self.widget_cache[tool_uuid]["result"] = result
            self.save_widget_cache()
        search_widget = self.widgets.get(codeblock, None)
        if search_widget is not None:
            GLib.idle_add(search_widget.finish, result)

    def add_website(self, term, title, link, favicon, tool_uuid):
        search_widget = self.widgets.get(term, None)
        if search_widget is not None:
            GLib.idle_add(search_widget.add_website, title, link, favicon)
        if tool_uuid:
            tool_uuid = str(tool_uuid)
            self.widget_cache[tool_uuid]["websites"].append((title, link, favicon))

    def load_search_widget(self, query, sources, result):
        from ..ui.widgets import WebSearchWidget
        widget = WebSearchWidget(query)
        for title, link, favicon in tuple(sources):
            widget.add_website(title, link, favicon)
        widget.finish(result)
        widget.connect("website-clicked", lambda widget,link : self.ui_controller.open_link(link, False, not self.settings.get_boolean("external-browser")))
        return widget

    def restore_gtk_widget(self, codeblock: str, lang: str, tool_uuid) -> Gtk.Widget | None:
        from ..ui.widgets import WebSearchWidget
        if tool_uuid:
            tool_uuid = str(tool_uuid)
        cache = self.widget_cache.get(tool_uuid, None)
        if cache is not None:
            return self.load_search_widget(codeblock, cache["websites"], cache["result"])
        else:
            search_widget = WebSearchWidget(codeblock)
            search_widget.finish("No result found")
        return search_widget

    def get_gtk_widget(self, codeblock: str, lang: str, tool_uuid) -> Gtk.Widget | None:
        from ..ui.widgets import WebSearchWidget
        self.tool_uuid = tool_uuid
        search_widget = WebSearchWidget(search_term=codeblock)
        search_widget.connect("website-clicked", lambda widget,link : self.ui_controller.open_link(link, False, not self.settings.get_boolean("external-browser")))
        self.widgets[codeblock] = search_widget
        if tool_uuid:
            tool_uuid = str(tool_uuid)
            self.widget_cache[tool_uuid] = {}
            self.widget_cache[tool_uuid]["websites"] = []
            self.widget_cache[tool_uuid]["result"] = "No result found"
        return search_widget

    def postprocess_history(self, history: list, bot_response: str) -> tuple[list, str]:
        chunks = get_message_chunks(bot_response)
        for chunk in chunks:
            if chunk.type == "codeblock" and chunk.lang == "search":
                bot_response = "```search\n" + chunk.text + "\n```"
                break
        return history, bot_response

    def save_widget_cache(self):
        with open(os.path.join(self.extension_path, "websearch_cache.json"), "w+") as f:
            json.dump(self.widget_cache, f)

    def load_widet_cache(self):
        if os.path.exists(os.path.join(self.extension_path, "websearch_cache.json")):
            with open(os.path.join(self.extension_path, "websearch_cache.json")) as f:
                self.widget_cache = json.load(f)
        else:
            self.widget_cache = {}

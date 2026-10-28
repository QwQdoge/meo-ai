# Cloud core view contract (v1)

`meo_ai_core::cloud::AppCore` owns all product state. A client:

1. creates the core with platform hooks (`changed()`, `open_url(url)`) and a storage
   implementation, dispatches `{"type":"start"}`;
2. renders `AppCore::view()` (JSON below) whenever `changed()` fires;
3. sends back the `action` object attached to the element the user activated, adding
   only user input fields (`text` for `send`, `value` for `set_setting`).

Clients must not interpret feature IDs; they render component kinds only.

## Root

| Field | Meaning |
| --- | --- |
| `schema` | View schema version (1) |
| `auth.state` | `signed_out` / `signing_in` / `signed_in`; `auth.email` |
| `online` | `false` → show an offline hint; cached data is still shown |
| `navigation[]` | `{id,label,icon,symbol,placement(primary/secondary),selected,action}`; empty when signed out |
| `page` | One of the page kinds below |
| `notice` | `{kind: error/info, text, action}` or `null` |
| `prefs` | Client preferences (e.g. `general.enter_to_send`, `appearance.theme`) |

## Page kinds

- `sign_in`: `title, text, busy, actions[]`
- `conversation`: `title`, `sidebar{title, actions[], items[{id,title,subtitle,selected,action}]}`,
  `messages[{role,text,streaming}]` (text is Markdown), `empty{title,text}|null`,
  `composer{placeholder,busy,sendAction,stopAction,toolbar[control]}`, `consent{title,text,actions[2]}|null`
- `list`: `title, loading?, items[{id,title,subtitle,action?}], empty{title}|null, actions[]`
- `settings`: `title, sections[{id,label,items[control]}]`
- `unavailable`: `title, text, actions[]`

`button` = `{label, style: primary/secondary/danger, action}`.
`control` = `{id,label,kind,binding,value,options[{value,label}],action?,style?}` with
`kind` ∈ `toggle | select | text | info | button`. Changing a control dispatches
`{"type":"set_setting","binding":…,"value":…}`; `button` dispatches its `action`.

## Slash commands and starters

`composer.commands[{name,hint,label}]` lists the `/commands` the core handles inside `send`
(`/new /model /search /retry /rename /archive /remember /help`; unknown `/words` are plain
text). Clients show the matching ones while the composer text is `/word` and either fill
`name + " "` (hint present) or send `name`. `empty.suggestions[{label,action}]` are starter
prompts rendered as chips; activating one dispatches its `send` action.

## Answer steps

An assistant message may carry `steps[{id,title,detail,status(running/done/error),items[{title,url}]}]`,
`stepsLabel` ("Working…" / "N steps") and `stepsOpen`. Clients render a collapsible list under
that label, expanded while `stepsOpen` is true (the core collapses it when the answer is done)
unless the user toggled it. Steps today: model route, web search (with result links), answer, image.

## Actions

`start, realtime, sign_in, sign_out, auth_callback{url}, navigate{route}, new_conversation,
select_conversation{id}, send{text}, stop, approve_consent, deny_consent,
set_setting{binding,value}, refresh, dismiss_notice`.

## Real-time sync

Hosts dispatch `realtime` once after `start`, as its own long-running task (extra calls
return at once). The core then keeps `GET /v1/realtime` (Meo API, one Durable Object per
user) open while signed in, reconnects with backoff and resyncs on every (re)connect.
Events from other devices (`conversation.changed`, `run.started/delta/done/error`; this
device's own `?client=` events are ignored) refresh the conversation list and active
messages, and an answer being generated elsewhere appears in `messages` as an assistant
message with `streaming: true`. Clients render nothing new: it is the same view.
The sender saves the user message before streaming so other devices see the prompt too.

## Hosts

- **Desktop** `desktop-rs`: Rust + QtBridge, renderer `qml/Main.qml`, loopback sign-in.
- **Android** `android/`: `org.meo.ai.core.CloudCore` wraps `AppCore` through JNI
  (`core-rs/src/android.rs`, feature `android-jni`: `nativeCreate/View/Dispatch/Destroy`);
  `ui/CoreApp.kt` is the Compose renderer; `MainActivity` only forwards the
  `org.meo.ai:/oauth/callback` redirect as `auth_callback`. The pending sign-in is persisted
  by the core, and `auth_callback` waits for `start`, so a cold start from the redirect works.
- **Web** `web/client`: the same core compiled to WASM (`core-rs` feature `wasm`, built by
  `scripts/build-core.mjs` into `$MEO_OUTPUT_ROOT/meo-ai/build/web-core`). `src/core/useCore.ts`
  hosts it (state in `localStorage`, sign-in is a same-tab PKCE redirect to
  `/oauth/openid/callback`, which the page hands to the core as `auth_callback`);
  `src/core/CoreApp.tsx` is the React renderer. The legacy BFF function there only handles
  the callback when it has its own flow cookie, otherwise it serves the app. The old
  `src/meo/*` product components are unused and can be deleted once the Web release is accepted.

## Documents and files (core-owned)

The core reads and writes document formats so every client behaves the same; a client only picks
or saves bytes.

- **Attach**: clients send `{"type":"attach_text","name","text"}` for text files and
  `{"type":"attach_image",...}` for pictures. For PDF, Word (docx), Excel (xlsx), PowerPoint (pptx)
  and RTF they send `{"type":"attach_document","name","data"}` (`data` is base64, up to 25 MB); the
  core extracts the text (`core-rs/src/cloud/docs.rs`) and attaches it like a text file.
- **Files the assistant writes**: a fenced block whose language line is `file:<name.ext>` becomes a
  block `{"type":"file","name","kind","action":{"type":"save_file","message","index"}}`. The client
  shows a card and sends the action; the core builds the bytes (`.docx` from Markdown, `.xlsx` from
  CSV, anything else as text) and calls the platform hook `save_file(name, bytes)`. A host that
  returns `false` (desktop, runner) gets the file in `~/Downloads`; the web hook is
  `window.meoSaveFile(name, bytes)`.

## Store page (`page.kind = "store"`)

The Skills route renders the plugin store. Fields: `tabs` (`discover`, `installed`, `import`), `filters`
(category chips), `search {value, placeholder, action, field}` (the client sends `action` plus
`{[field]: text}`), `sections[]` with `cards[]` (`title`, `subtitle`, `publisher`, `badges`, `state`:
`available|installed|on|off`, `icon`, `actions`), `forms[]` (import inputs, same `action`+`field`
convention) and `links[]`. `icon` is `{svg, color}` (a 24x24 path), `{glyph, color}` (a Material
Symbols name) or null (draw a letter tile). Actions: `store_tab`, `store_filter`, `store_search`,
`install_plugin`, `install_registry`, `import_skill`, `import_mcp`, `uninstall_plugin`,
`toggle_plugin`. An action `{type:"open_link", url}` is handled by the client itself (open in a new tab).

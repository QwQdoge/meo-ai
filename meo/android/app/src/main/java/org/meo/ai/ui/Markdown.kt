package org.meo.ai.ui

import java.util.UUID
import org.json.JSONArray
import org.json.JSONObject

/** Wraps Markdown text from the core as the single ContentBlock array `RichBlockRenderer` renders. */
fun markdownBlocks(text: String): String {
    if (text.isBlank()) return "[]"
    return JSONArray().put(
        JSONObject()
            .put("type", "markdown")
            .put("block_id", "android:${UUID.randomUUID()}")
            .put("text", text),
    ).toString()
}

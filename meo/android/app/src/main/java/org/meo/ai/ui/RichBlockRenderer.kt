package org.meo.ai.ui

import android.os.Build
import android.webkit.WebSettings
import android.webkit.WebView
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import coil3.compose.AsyncImage
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.max

@Composable
fun RichBlockRenderer(
    blocksJson: String,
    modifier: Modifier = Modifier,
    onAction: (String) -> Unit = {},
) {
    val blocks = remember(blocksJson) {
        runCatching { JSONArray(blocksJson) }.getOrElse { JSONArray() }
    }
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(10.dp)) {
        for (index in 0 until blocks.length()) {
            blocks.optJSONObject(index)?.let { block ->
                RichBlock(block = block, onAction = onAction)
            }
        }
    }
}

@Composable
private fun RichBlock(block: JSONObject, onAction: (String) -> Unit) {
    when (block.optString("type")) {
        "text" -> Text(block.optString("text"), style = MaterialTheme.typography.bodyLarge)
        "markdown" -> MarkdownBlock(block.optString("text"))
        "code" -> CodeBlock(block)
        "math" -> MathBlock(block)
        "image" -> ImageBlock(block)
        "attachment", "artifact" -> AttachmentBlock(block)
        "citation" -> CitationBlock(block)
        "source_group" -> SourceGroupBlock(block)
        "tool_activity" -> ToolBlock(block)
        "confirmation" -> ConfirmationBlock(block, onAction)
        "presentation" -> PresentationBlock(block)
        "chart" -> ChartBlock(block)
        "table" -> TableBlock(block)
        "html" -> HtmlBlock(block)
        "plugin" -> PluginBlock(block, onAction)
        "error" -> ErrorBlock(block)
        else -> Text(
            text = "Unsupported block: ${block.optString("type", "unknown")}",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.labelMedium,
        )
    }
}

@Composable
private fun MarkdownBlock(text: String) {
    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
        text.lines().forEach { rawLine ->
            when {
                rawLine.startsWith("### ") -> Text(
                    inlineMarkdown(rawLine.drop(4)),
                    style = MaterialTheme.typography.titleMedium,
                )
                rawLine.startsWith("## ") -> Text(
                    inlineMarkdown(rawLine.drop(3)),
                    style = MaterialTheme.typography.titleLarge,
                )
                rawLine.startsWith("# ") -> Text(
                    inlineMarkdown(rawLine.drop(2)),
                    style = MaterialTheme.typography.headlineSmall,
                )
                rawLine.startsWith("- ") -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("•")
                    Text(inlineMarkdown(rawLine.drop(2)), style = MaterialTheme.typography.bodyLarge)
                }
                rawLine.isBlank() -> Spacer(Modifier.height(2.dp))
                else -> Text(inlineMarkdown(rawLine), style = MaterialTheme.typography.bodyLarge)
            }
        }
    }
}

private fun inlineMarkdown(text: String) = buildAnnotatedString {
    var index = 0
    while (index < text.length) {
        when {
            text.startsWith("**", index) -> {
                val end = text.indexOf("**", index + 2)
                if (end > index + 2) {
                    pushStyle(SpanStyle(fontWeight = FontWeight.SemiBold))
                    append(text.substring(index + 2, end))
                    pop()
                    index = end + 2
                } else {
                    append(text[index++])
                }
            }
            text[index] == '`' -> {
                val end = text.indexOf('`', index + 1)
                if (end > index + 1) {
                    pushStyle(SpanStyle(fontFamily = FontFamily.Monospace))
                    append(text.substring(index + 1, end))
                    pop()
                    index = end + 1
                } else {
                    append(text[index++])
                }
            }
            else -> append(text[index++])
        }
    }
}

@Composable
private fun CodeBlock(block: JSONObject) {
    Surface(
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.surfaceContainerHigh,
    ) {
        Column {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    block.optString("filename").ifBlank { block.optString("language", "code") },
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text("Code", style = MaterialTheme.typography.labelSmall)
            }
            HorizontalDivider()
            SelectionContainer {
                Text(
                    text = block.optString("text"),
                    modifier = Modifier.padding(14.dp).horizontalScroll(rememberScrollState()),
                    fontFamily = FontFamily.Monospace,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
    }
}

@Composable
private fun MathBlock(block: JSONObject) {
    Surface(
        shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.surfaceContainerLow,
    ) {
        SelectionContainer {
            Text(
                text = block.optString("latex"),
                modifier = Modifier.fillMaxWidth().padding(14.dp),
                fontFamily = FontFamily.Serif,
                style = if (block.optBoolean("display")) MaterialTheme.typography.titleMedium
                else MaterialTheme.typography.bodyLarge,
            )
        }
    }
}

@Composable
private fun ImageBlock(block: JSONObject) {
    val uri = block.optString("uri").ifBlank { block.optString("resource_uri") }
    Card(shape = RoundedCornerShape(20.dp)) {
        if (uri.isNotBlank()) {
            AsyncImage(
                model = uri,
                contentDescription = block.optString("alt").ifBlank { block.optString("name") },
                modifier = Modifier.fillMaxWidth(),
            )
        } else {
            Box(
                modifier = Modifier.fillMaxWidth().height(180.dp)
                    .background(MaterialTheme.colorScheme.surfaceContainerHigh),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    block.optString("name", "Image"),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun AttachmentBlock(block: JSONObject) {
    Surface(
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.surfaceContainerLow,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Box(
                Modifier.size(38.dp).background(
                    MaterialTheme.colorScheme.secondaryContainer,
                    RoundedCornerShape(12.dp),
                ),
                contentAlignment = Alignment.Center,
            ) { Text("↗") }
            Column(Modifier.weight(1f)) {
                Text(block.optString("name", "Attachment"), fontWeight = FontWeight.Medium)
                Text(
                    block.optString("mime_type").ifBlank { block.optString("state") },
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun CitationBlock(block: JSONObject) {
    val uriHandler = LocalUriHandler.current
    OutlinedButton(
        onClick = {
            block.optString("uri").takeIf { it.startsWith("https://") || it.startsWith("http://") }
                ?.let(uriHandler::openUri)
        },
        enabled = block.optString("uri").isNotBlank(),
    ) {
        Text(block.optString("label", "Source"), maxLines = 2)
    }
}

@Composable
private fun SourceGroupBlock(block: JSONObject) {
    val sources = block.optJSONArray("sources") ?: JSONArray()
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        block.optString("title").takeIf { it.isNotBlank() }?.let {
            Text(it, style = MaterialTheme.typography.titleSmall)
        }
        for (index in 0 until sources.length()) {
            val source = sources.optJSONObject(index) ?: continue
            CitationBlock(source.put("type", "citation"))
        }
    }
}

@Composable
private fun ToolBlock(block: JSONObject) {
    val state = block.optString("state")
    Surface(
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.surfaceContainerLow,
    ) {
        Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(block.optString("title", "Tool"), fontWeight = FontWeight.Medium)
                AssistChip(onClick = {}, label = { Text(state.replace('_', ' ')) })
            }
            block.optString("detail").takeIf { it.isNotBlank() }?.let {
                Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (state == "running" || state == "queued") LinearProgressIndicator(Modifier.fillMaxWidth())
        }
    }
}

@Composable
private fun ConfirmationBlock(block: JSONObject, onAction: (String) -> Unit) {
    val actions = block.optJSONArray("actions") ?: JSONArray()
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer),
        shape = RoundedCornerShape(20.dp),
    ) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(block.optString("title", "Confirmation required"), style = MaterialTheme.typography.titleMedium)
            Text(block.optString("detail"), color = MaterialTheme.colorScheme.onSecondaryContainer)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (index in 0 until actions.length()) {
                    val action = actions.optJSONObject(index) ?: continue
                    Button(onClick = { onAction(action.optString("action_id")) }) {
                        Text(action.optString("label", "Continue"))
                    }
                }
            }
        }
    }
}

@Composable
private fun PresentationBlock(block: JSONObject) {
    Surface(
        shape = RoundedCornerShape(20.dp),
        color = MaterialTheme.colorScheme.tertiaryContainer,
    ) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text(block.optString("title"), style = MaterialTheme.typography.titleMedium)
            block.optString("value").takeIf { it.isNotBlank() }?.let {
                Text(it, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
            }
            Text(block.optString("detail"), color = MaterialTheme.colorScheme.onTertiaryContainer)
        }
    }
}

@Composable
private fun ChartBlock(block: JSONObject) {
    val data = block.optJSONArray("data") ?: JSONArray()
    val series = block.optJSONArray("series") ?: JSONArray()
    val valueKey = series.optJSONObject(0)?.optString("key").orEmpty()
    val values = (0 until data.length()).mapNotNull {
        data.optJSONObject(it)?.optDouble(valueKey)?.takeIf(Double::isFinite)?.toFloat()
    }
    val maxValue = max(values.maxOrNull() ?: 1f, 1f)
    val chartColor = MaterialTheme.colorScheme.primary
    val gridColor = MaterialTheme.colorScheme.outlineVariant
    val kind = block.optString("kind", "bar")

    Surface(shape = RoundedCornerShape(20.dp), color = MaterialTheme.colorScheme.surfaceContainerLow) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(block.optString("title", "Chart"), style = MaterialTheme.typography.titleMedium)
            Canvas(Modifier.fillMaxWidth().height(190.dp)) {
                drawLine(gridColor, Offset(0f, size.height), Offset(size.width, size.height), strokeWidth = 1f)
                if (values.isEmpty()) return@Canvas
                when (kind) {
                    "line", "area" -> {
                        val path = Path()
                        values.forEachIndexed { index, value ->
                            val x = if (values.size == 1) size.width / 2 else size.width * index / (values.size - 1)
                            val y = size.height - (value / maxValue) * size.height * 0.9f
                            if (index == 0) path.moveTo(x, y) else path.lineTo(x, y)
                        }
                        drawPath(path, chartColor, style = Stroke(width = 4f))
                    }
                    "scatter" -> values.forEachIndexed { index, value ->
                        val x = size.width * (index + 1) / (values.size + 1)
                        val y = size.height - (value / maxValue) * size.height * 0.9f
                        drawCircle(chartColor, radius = 7f, center = Offset(x, y))
                    }
                    "pie" -> {
                        val total = values.sum().takeIf { it > 0f } ?: 1f
                        var start = -90f
                        values.forEachIndexed { index, value ->
                            val sweep = 360f * value / total
                            drawArc(
                                color = chartColor.copy(alpha = 1f - index.coerceAtMost(6) * 0.1f),
                                startAngle = start,
                                sweepAngle = sweep,
                                useCenter = true,
                                topLeft = Offset(size.width * 0.22f, 0f),
                                size = Size(size.height, size.height),
                            )
                            start += sweep
                        }
                    }
                    else -> {
                        val slot = size.width / values.size
                        values.forEachIndexed { index, value ->
                            val height = (value / maxValue) * size.height * 0.9f
                            drawRoundRect(
                                color = chartColor,
                                topLeft = Offset(index * slot + slot * 0.18f, size.height - height),
                                size = Size(slot * 0.64f, height),
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun TableBlock(block: JSONObject) {
    val columns = block.optJSONArray("columns") ?: JSONArray()
    val rows = block.optJSONArray("rows") ?: JSONArray()
    val scroll = rememberScrollState()
    Surface(shape = RoundedCornerShape(18.dp), color = MaterialTheme.colorScheme.surfaceContainerLow) {
        Column(Modifier.horizontalScroll(scroll).padding(12.dp)) {
            block.optString("title").takeIf { it.isNotBlank() }?.let {
                Text(it, style = MaterialTheme.typography.titleSmall, modifier = Modifier.padding(6.dp))
            }
            Row {
                for (index in 0 until columns.length()) {
                    val column = columns.optJSONObject(index) ?: continue
                    Text(
                        column.optString("label", column.optString("key")),
                        modifier = Modifier.width(140.dp).padding(8.dp),
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }
            HorizontalDivider()
            for (rowIndex in 0 until rows.length()) {
                val row = rows.optJSONObject(rowIndex) ?: continue
                Row {
                    for (columnIndex in 0 until columns.length()) {
                        val column = columns.optJSONObject(columnIndex) ?: continue
                        Text(
                            row.opt(column.optString("key"))?.toString().orEmpty(),
                            modifier = Modifier.width(140.dp).padding(8.dp),
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun HtmlBlock(block: JSONObject) {
    val html = block.optString("html")
    val sandbox = block.optString("sandbox", "static")
    Surface(shape = RoundedCornerShape(18.dp), color = MaterialTheme.colorScheme.surfaceContainerLow) {
        Column {
            block.optString("title").takeIf { it.isNotBlank() }?.let {
                Text(it, style = MaterialTheme.typography.titleSmall, modifier = Modifier.padding(14.dp))
            }
            AndroidView(
                modifier = Modifier.fillMaxWidth().height(260.dp),
                factory = { context ->
                    WebView(context).apply {
                        settings.javaScriptEnabled = sandbox != "static"
                        settings.domStorageEnabled = sandbox == "interactive"
                        settings.allowFileAccess = false
                        settings.allowContentAccess = false
                        settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) settings.safeBrowsingEnabled = true
                    }
                },
                update = { webView ->
                    webView.settings.javaScriptEnabled = sandbox != "static"
                    webView.settings.domStorageEnabled = sandbox == "interactive"
                    webView.loadDataWithBaseURL("https://meo.invalid/", html, "text/html", "utf-8", null)
                },
            )
        }
    }
}

@Composable
private fun PluginBlock(block: JSONObject, onAction: (String) -> Unit) {
    val presentation = block.optJSONObject("presentation") ?: JSONObject()
    val actions = presentation.optJSONArray("actions") ?: JSONArray()
    Card(shape = RoundedCornerShape(22.dp)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Column {
                    Text(presentation.optString("plugin_name", "Plugin"), style = MaterialTheme.typography.labelMedium)
                    Text(presentation.optString("title"), style = MaterialTheme.typography.titleMedium)
                }
                AssistChip(onClick = {}, label = { Text("Connected") })
            }
            presentation.optString("subtitle").takeIf { it.isNotBlank() }?.let {
                Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            presentation.opt("body")?.let {
                Text(it.toString(), style = MaterialTheme.typography.bodyMedium)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (index in 0 until actions.length()) {
                    val action = actions.optJSONObject(index) ?: continue
                    OutlinedButton(onClick = { onAction(action.optString("action_id")) }) {
                        Text(action.optString("label", "Open"))
                    }
                }
            }
        }
    }
}

@Composable
private fun ErrorBlock(block: JSONObject) {
    Surface(
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.errorContainer,
    ) {
        Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text(block.optString("title", "Something went wrong"), fontWeight = FontWeight.SemiBold)
            Text(block.optString("detail"), color = MaterialTheme.colorScheme.onErrorContainer)
        }
    }
}

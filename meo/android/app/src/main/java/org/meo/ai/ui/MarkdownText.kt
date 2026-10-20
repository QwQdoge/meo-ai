package org.meo.ai.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.ClickableText
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// Markdown for model answers: headings, paragraphs, bullet and numbered lists
// (nested), block quotes, fenced code with a copy button, tables, rules and the
// usual inline styles. Fences that are still streaming (no closing fence yet)
// render as code too, so a half-written block never shows raw backticks.

internal sealed interface MdBlock {
    data class Heading(val level: Int, val text: String) : MdBlock
    data class Paragraph(val text: String) : MdBlock
    data class Code(val language: String, val code: String) : MdBlock
    data class Item(val marker: String, val depth: Int, val text: String) : MdBlock
    data class Quote(val text: String) : MdBlock
    data class Table(val header: List<String>, val rows: List<List<String>>) : MdBlock
    data object Rule : MdBlock
}

private val fence = Regex("^\\s*(```+|~~~+)\\s*([\\w+#.-]*)\\s*$")
private val heading = Regex("^(#{1,6})\\s+(.*?)\\s*#*\\s*$")
private val listItem = Regex("^(\\s*)([-*+]|\\d{1,9}[.)])\\s+(.*)$")
private val rule = Regex("^\\s*([-*_])(\\s*\\1){2,}\\s*$")
private val tableSeparator = Regex("^\\s*\\|?\\s*:?-+:?\\s*(\\|\\s*:?-+:?\\s*)*\\|?\\s*$")

private fun cells(line: String): List<String> =
    line.trim().trim('|').split('|').map { it.trim() }

internal fun parseMarkdown(source: String): List<MdBlock> {
    val lines = source.replace("\r\n", "\n").split('\n')
    val blocks = mutableListOf<MdBlock>()
    val paragraph = mutableListOf<String>()
    fun flush() {
        if (paragraph.isNotEmpty()) blocks += MdBlock.Paragraph(paragraph.joinToString("\n")).also { paragraph.clear() }
    }
    var i = 0
    while (i < lines.size) {
        val line = lines[i]
        val open = fence.matchEntire(line)
        when {
            open != null -> {
                flush()
                val mark = open.groupValues[1]
                val body = mutableListOf<String>()
                i++
                while (i < lines.size && !lines[i].trim().startsWith(mark.take(3)) ) { body += lines[i]; i++ }
                blocks += MdBlock.Code(open.groupValues[2], body.joinToString("\n"))
            }
            line.isBlank() -> flush()
            rule.matches(line) -> { flush(); blocks += MdBlock.Rule }
            heading.matches(line) -> {
                flush()
                val m = heading.matchEntire(line)!!
                blocks += MdBlock.Heading(m.groupValues[1].length, m.groupValues[2])
            }
            line.contains('|') && i + 1 < lines.size && tableSeparator.matches(lines[i + 1]) -> {
                flush()
                val header = cells(line)
                val rows = mutableListOf<List<String>>()
                i += 2
                while (i < lines.size && lines[i].contains('|') && lines[i].isNotBlank()) { rows += cells(lines[i]); i++ }
                blocks += MdBlock.Table(header, rows)
                continue
            }
            line.trimStart().startsWith(">") -> {
                flush()
                val quote = mutableListOf<String>()
                while (i < lines.size && lines[i].trimStart().startsWith(">")) {
                    quote += lines[i].trimStart().removePrefix(">").removePrefix(" ")
                    i++
                }
                blocks += MdBlock.Quote(quote.joinToString("\n"))
                continue
            }
            listItem.matches(line) -> {
                flush()
                val m = listItem.matchEntire(line)!!
                val marker = m.groupValues[2].let { if (it[0].isDigit()) it else "•" }
                blocks += MdBlock.Item(marker, m.groupValues[1].length / 2, m.groupValues[3])
            }
            else -> paragraph += line.trimEnd()
        }
        i++
    }
    flush()
    return blocks
}

private val inlineToken = Regex(
    "`([^`\\n]+)`|\\*\\*(.+?)\\*\\*|__(.+?)__|~~(.+?)~~|\\[([^\\]]+)]\\((https?://[^)\\s]+)\\)|\\*([^*\\n]+)\\*|(?<![\\w])_([^_\\n]+)_(?![\\w])",
)

@Composable
private fun inline(text: String, codeBackground: androidx.compose.ui.graphics.Color, link: androidx.compose.ui.graphics.Color): AnnotatedString =
    buildAnnotatedString {
        var cursor = 0
        for (m in inlineToken.findAll(text)) {
            append(text.substring(cursor, m.range.first))
            val g = m.groupValues
            when {
                g[1].isNotEmpty() -> withStyle(SpanStyle(fontFamily = FontFamily.Monospace, background = codeBackground)) { append(g[1]) }
                g[2].isNotEmpty() -> withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(g[2]) }
                g[3].isNotEmpty() -> withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(g[3]) }
                g[4].isNotEmpty() -> withStyle(SpanStyle(textDecoration = TextDecoration.LineThrough)) { append(g[4]) }
                g[5].isNotEmpty() -> {
                    pushStringAnnotation("url", g[6])
                    withStyle(SpanStyle(color = link, textDecoration = TextDecoration.Underline)) { append(g[5]) }
                    pop()
                }
                g[7].isNotEmpty() -> withStyle(SpanStyle(fontStyle = FontStyle.Italic)) { append(g[7]) }
                g[8].isNotEmpty() -> withStyle(SpanStyle(fontStyle = FontStyle.Italic)) { append(g[8]) }
            }
            cursor = m.range.last + 1
        }
        append(text.substring(cursor))
    }

@Composable
private fun Rich(text: String, modifier: Modifier = Modifier, style: androidx.compose.ui.text.TextStyle = MaterialTheme.typography.bodyLarge) {
    val scheme = MaterialTheme.colorScheme
    val uri = LocalUriHandler.current
    val annotated = inline(text, scheme.surfaceContainerHigh, scheme.primary)
    ClickableText(
        text = annotated,
        modifier = modifier,
        style = style.copy(color = scheme.onSurface),
        onClick = { offset ->
            annotated.getStringAnnotations("url", offset, offset).firstOrNull()?.let { runCatching { uri.openUri(it.item) } }
        },
    )
}

@Composable
fun MarkdownText(text: String, modifier: Modifier = Modifier) {
    val blocks = remember(text) { parseMarkdown(text) }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(10.dp)) {
        blocks.forEach { block ->
            when (block) {
                is MdBlock.Heading -> Rich(
                    block.text,
                    style = when (block.level) {
                        1 -> MaterialTheme.typography.headlineSmall
                        2 -> MaterialTheme.typography.titleLarge
                        else -> MaterialTheme.typography.titleMedium
                    },
                )
                is MdBlock.Paragraph -> Rich(block.text)
                is MdBlock.Item -> Row(Modifier.padding(start = (block.depth * 16).dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(block.marker, style = MaterialTheme.typography.bodyLarge)
                    Rich(block.text)
                }
                is MdBlock.Quote -> Row(Modifier.height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Box(Modifier.width(3.dp).fillMaxHeight().background(MaterialTheme.colorScheme.outline))
                    Rich(block.text, style = MaterialTheme.typography.bodyLarge.copy(fontStyle = FontStyle.Italic))
                }
                is MdBlock.Code -> CodeBlockView(block)
                is MdBlock.Table -> TableView(block)
                MdBlock.Rule -> HorizontalDivider()
            }
        }
    }
}

@Composable
private fun CodeBlockView(block: MdBlock.Code) {
    val clipboard = LocalClipboardManager.current
    Surface(shape = RoundedCornerShape(14.dp), color = MaterialTheme.colorScheme.surfaceContainerHigh) {
        Column {
            Row(Modifier.fillMaxWidth().padding(start = 14.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(
                    block.language.ifBlank { "code" },
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 12.dp),
                )
                TextButton(onClick = { clipboard.setText(AnnotatedString(block.code)) }) { Text("Copy") }
            }
            Text(
                block.code,
                modifier = Modifier.padding(start = 14.dp, end = 14.dp, bottom = 14.dp).horizontalScroll(rememberScrollState()),
                fontFamily = FontFamily.Monospace,
                fontSize = 13.sp,
                softWrap = false,
            )
        }
    }
}

@Composable
private fun TableView(table: MdBlock.Table) {
    val line = MaterialTheme.colorScheme.outlineVariant
    Column(Modifier.horizontalScroll(rememberScrollState()).border(1.dp, line, RoundedCornerShape(8.dp))) {
        (listOf(table.header) + table.rows).forEachIndexed { index, row ->
            Row(Modifier.then(if (index > 0) Modifier.border(0.5.dp, line) else Modifier)) {
                row.forEach { cell ->
                    Box(Modifier.width(140.dp).padding(horizontal = 10.dp, vertical = 8.dp)) {
                        val annotated = inline(cell, MaterialTheme.colorScheme.surfaceContainerHigh, MaterialTheme.colorScheme.primary)
                        Text(
                            annotated,
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = if (index == 0) FontWeight.Bold else FontWeight.Normal,
                        )
                    }
                }
            }
        }
    }
    Spacer(Modifier.height(2.dp))
}

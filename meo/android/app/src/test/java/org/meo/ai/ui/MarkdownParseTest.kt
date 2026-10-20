package org.meo.ai.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MarkdownParseTest {
    @Test
    fun fencedCodeKeepsItsContentAndLanguage() {
        val blocks = parseMarkdown("Intro\n\n```rust\nfn main() {\n    println!(\"hi\");\n}\n```\nAfter")
        assertEquals(MdBlock.Paragraph("Intro"), blocks[0])
        assertEquals(MdBlock.Code("rust", "fn main() {\n    println!(\"hi\");\n}"), blocks[1])
        assertEquals(MdBlock.Paragraph("After"), blocks[2])
    }

    @Test
    fun anUnfinishedFenceWhileStreamingStillRendersAsCode() {
        val blocks = parseMarkdown("```python\nprint(1)")
        assertEquals(listOf<MdBlock>(MdBlock.Code("python", "print(1)")), blocks)
    }

    @Test
    fun listsKeepNumbersAndNesting() {
        val blocks = parseMarkdown("1. one\n2. two\n  - nested\n- bullet")
        assertEquals(MdBlock.Item("1.", 0, "one"), blocks[0])
        assertEquals(MdBlock.Item("2.", 0, "two"), blocks[1])
        assertEquals(MdBlock.Item("•", 1, "nested"), blocks[2])
        assertEquals(MdBlock.Item("•", 0, "bullet"), blocks[3])
    }

    @Test
    fun tablesNeedTheSeparatorRow() {
        val table = parseMarkdown("| a | b |\n|---|:-:|\n| 1 | 2 |\n| 3 | 4 |").single() as MdBlock.Table
        assertEquals(listOf("a", "b"), table.header)
        assertEquals(listOf(listOf("1", "2"), listOf("3", "4")), table.rows)
        assertTrue(parseMarkdown("a | b\nplain").single() is MdBlock.Paragraph)
    }

    @Test
    fun headingsQuotesAndRules() {
        val blocks = parseMarkdown("## Title\n> quoted\n> more\n\n---\ntext")
        assertEquals(MdBlock.Heading(2, "Title"), blocks[0])
        assertEquals(MdBlock.Quote("quoted\nmore"), blocks[1])
        assertEquals(MdBlock.Rule, blocks[2])
        assertEquals(MdBlock.Paragraph("text"), blocks[3])
    }
}

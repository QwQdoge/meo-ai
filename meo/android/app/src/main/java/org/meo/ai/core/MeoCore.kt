package org.meo.ai.core

class MeoCore private constructor() {
    companion object {
        val available: Boolean = runCatching {
            System.loadLibrary("meo_ai_core")
            true
        }.getOrDefault(false)

        @JvmStatic
        external fun normalizeSseEvent(line: String): String

        @JvmStatic
        external fun normalizeBlocks(blocksJson: String): String
    }
}

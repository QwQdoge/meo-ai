package org.meo.ai

/** Accept Kotlin function values without relying on Java SAM conversion at call sites. */
fun MainActivity.runOnUiThread(block: () -> Unit) {
    runOnUiThread(Runnable { block() })
}

package org.meo.ai.core

import android.content.ActivityNotFoundException
import androidx.browser.customtabs.CustomTabsIntent
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Handler
import android.os.Looper
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean
import org.json.JSONObject

/** Called by the Rust core from its own threads. */
interface CloudCoreListener {
    fun onChanged()
    fun onOpenUrl(url: String)
}

/**
 * Handle to the shared Rust application core (`meo_ai_core::cloud::AppCore`).
 *
 * The core owns sign-in, Meo API access, caching, navigation and page content.
 * This class only exposes its JSON [view] to Compose and forwards action
 * objects back; it contains no product logic.
 */
class CloudCore(private val context: Context, clientId: String) : CloudCoreListener {
    /** Latest view from the core; replaced (new instance) on every change. */
    var view: JSONObject by mutableStateOf(JSONObject())
        private set

    private val main = Handler(Looper.getMainLooper())
    private val refreshPending = AtomicBoolean(false)

    @Volatile
    private var handle = 0L

    init {
        if (available) {
            val dir = File(context.filesDir, "cloud").absolutePath
            handle = nativeCreate(dir, clientId, this)
            if (handle != 0L) {
                refresh()
                dispatch(JSONObject().put("type", "start"))
                // Live sync with the user's other devices.
                dispatch(JSONObject().put("type", "realtime"))
            }
        }
    }

    /** Sends an action object taken from [view] (plus any user input fields) to the core. */
    fun dispatch(action: JSONObject) {
        val h = handle
        if (h != 0L) nativeDispatch(h, action.toString())
    }

    fun close() {
        val h = handle
        handle = 0L
        if (h != 0L) nativeDestroy(h)
    }

    override fun onChanged() {
        // Coalesce bursts (streamed tokens) into one main-thread refresh per frame.
        if (refreshPending.compareAndSet(false, true)) main.post { refresh() }
    }

    override fun onOpenUrl(url: String) {
        main.post {
            // A Custom Tab is the system browser shown in-app (RFC 8252): passkeys, saved
            // passwords and the existing Account session work, which an embedded
            // WebView would not provide.
            val tab = CustomTabsIntent.Builder().setShowTitle(true).build()
            tab.intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            try {
                tab.launchUrl(context, Uri.parse(url))
            } catch (_: ActivityNotFoundException) {
                // No browser installed: the core keeps showing the sign-in page.
            }
        }
    }

    private fun refresh() {
        refreshPending.set(false)
        val h = handle
        if (h == 0L) return
        view = runCatching { JSONObject(nativeView(h)) }.getOrDefault(JSONObject())
    }

    companion object {
        val available: Boolean = runCatching {
            System.loadLibrary("meo_ai_core")
            true
        }.getOrDefault(false)

        @JvmStatic
        external fun nativeCreate(dataDir: String, clientId: String, listener: CloudCoreListener): Long

        @JvmStatic
        external fun nativeView(handle: Long): String

        @JvmStatic
        external fun nativeDispatch(handle: Long, action: String)

        @JvmStatic
        external fun nativeDestroy(handle: Long)
    }
}

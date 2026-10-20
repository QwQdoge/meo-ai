package org.meo.ai.core

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
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
    fun onNotify(title: String, text: String)
    fun onBusy(busy: Boolean)
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
                dispatch(JSONObject().put("type", "set_locale").put("locale", java.util.Locale.getDefault().toLanguageTag()))
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

    /** Keeps the process (and its network) alive while an answer is generated, even in the background. */
    override fun onBusy(busy: Boolean) {
        main.post {
            val intent = Intent(context, org.meo.ai.RunService::class.java)
            if (busy) runCatching { context.startForegroundService(intent) } else context.stopService(intent)
        }
    }

    /** A finished answer while the app is in the background (the core decides when). */
    override fun onNotify(title: String, text: String) {
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        manager.createNotificationChannel(NotificationChannel("answers", "Answers", NotificationManager.IMPORTANCE_DEFAULT))
        val open = PendingIntent.getActivity(
            context, 0,
            Intent(context, org.meo.ai.MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val notification = Notification.Builder(context, "answers")
            .setSmallIcon(android.R.drawable.stat_notify_chat)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(Notification.BigTextStyle().bigText(text))
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        // Silently skipped when the notification permission was not granted.
        runCatching { manager.notify(title.hashCode(), notification) }
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

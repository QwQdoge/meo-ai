package org.meo.ai

import android.app.Application
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.lifecycle.AndroidViewModel
import org.json.JSONObject
import org.meo.ai.core.CloudCore
import org.meo.ai.ui.CoreApp
import org.meo.ai.ui.MeoExpressiveTheme

/** Keeps the shared core alive across configuration changes. */
class CoreModel(application: Application) : AndroidViewModel(application) {
    val core = CloudCore(application, BuildConfig.MEO_OAUTH_CLIENT_ID)

    override fun onCleared() {
        core.close()
    }
}

/**
 * Thin host for the shared Rust core: it renders the core's view and forwards
 * actions. The only platform logic is delivering the OAuth redirect.
 */
class MainActivity : ComponentActivity() {
    private val model: CoreModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        if (android.os.Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED
        ) {
            // Needed to tell you when an answer finishes while the app is in the background.
            requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 1)
        }
        if (savedInstanceState == null) deliverCallback(intent?.data)
        setContent {
            val view = model.core.view
            val prefs = view.optJSONObject("prefs")
            MeoExpressiveTheme(
                themeMode = prefs?.optString("appearance.theme", "system")
                    ?.takeIf { it in setOf("system", "light", "dark") } ?: "system",
                reduceMotion = prefs?.optBoolean("appearance.reduce_motion", false) ?: false,
            ) {
                // Settings > Appearance > Text size scales every sp size.
                val density = androidx.compose.ui.platform.LocalDensity.current
                val factor = when (prefs?.optString("appearance.text_size", "default")) { "small" -> 0.9f; "large" -> 1.15f; else -> 1f }
                androidx.compose.runtime.CompositionLocalProvider(
                    androidx.compose.ui.platform.LocalDensity provides androidx.compose.ui.unit.Density(density.density, density.fontScale * factor),
                ) {
                    CoreApp(view, model.core::dispatch)
                }
            }
        }
    }

    // The core has no clock of its own: it delivers scheduled tasks on this tick while the app is open.
    private val clock = android.os.Handler(android.os.Looper.getMainLooper())
    private val tick = object : Runnable {
        override fun run() {
            val offset = java.util.TimeZone.getDefault().getOffset(System.currentTimeMillis()) / 60000
            model.core.dispatch(JSONObject().put("type", "tick").put("utc_offset_min", offset))
            clock.postDelayed(this, 15000)
        }
    }

    override fun onStart() {
        super.onStart()
        model.core.dispatch(JSONObject().put("type", "set_foreground").put("visible", true))
        clock.postDelayed(tick, 3000)
    }

    override fun onStop() {
        clock.removeCallbacks(tick)
        model.core.dispatch(JSONObject().put("type", "set_foreground").put("visible", false))
        super.onStop()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        deliverCallback(intent.data)
    }

    /** `org.meo.ai:/oauth/callback?code=…&state=…` from the browser sign-in. */
    private fun deliverCallback(uri: Uri?) {
        if (uri == null || uri.scheme != "org.meo.ai" || uri.path != "/oauth/callback") return
        model.core.dispatch(JSONObject().put("type", "auth_callback").put("url", uri.toString()))
    }
}

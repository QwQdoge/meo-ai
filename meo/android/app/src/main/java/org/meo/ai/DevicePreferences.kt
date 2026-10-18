package org.meo.ai

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

data class DevicePreferenceValues(
    val enterToSend: Boolean = true,
    val theme: String = "system",
    val reduceMotion: Boolean = false,
)

/** Device interaction preferences only. Account data and credentials never enter this store. */
class DevicePreferences(context: Context) {
    private val store = context.getSharedPreferences("meo-device-preferences-v1", Context.MODE_PRIVATE)
    var values by mutableStateOf(DevicePreferenceValues(
        enterToSend = store.getBoolean("general.enter_to_send", true),
        theme = store.getString("appearance.theme", "system").takeIf { it in listOf("system", "light", "dark") } ?: "system",
        reduceMotion = store.getBoolean("appearance.reduce_motion", false),
    ))
        private set

    fun update(value: DevicePreferenceValues) {
        require(value.theme in listOf("system", "light", "dark"))
        store.edit().putBoolean("general.enter_to_send", value.enterToSend)
            .putString("appearance.theme", value.theme)
            .putBoolean("appearance.reduce_motion", value.reduceMotion).apply()
        values = value
    }
}

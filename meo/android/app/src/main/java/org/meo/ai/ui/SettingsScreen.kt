package org.meo.ai.ui

import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import org.meo.ai.MeoController
import org.meo.ai.R
import org.meo.ai.schema.MeoUiSchema

private data class SettingsGroup(val id: String, val label: String, val fields: List<String>)
private val groups: List<SettingsGroup> by lazy {
    val rows = JSONObject(MeoUiSchema.json).getJSONObject("settings").getJSONArray("sections")
    List(rows.length()) { index -> rows.getJSONObject(index).let { SettingsGroup(it.getString("id"), it.getString("label"), it.getJSONArray("items").let { fields -> List(fields.length()) { index -> fields.getJSONObject(index).getString("id") } }) } }
}
private fun labelResource(id: String): Int = when(id) {
    "general" -> R.string.meo_settings_general
    "personalization" -> R.string.meo_settings_personalization
    "models" -> R.string.meo_settings_models
    "connectors" -> R.string.meo_settings_connectors
    "devices" -> R.string.meo_settings_devices
    "privacy" -> R.string.meo_settings_privacy
    "usage" -> R.string.meo_settings_usage
    "account" -> R.string.meo_settings_account
    else -> R.string.meo_settings_title
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(controller: MeoController, onClose: () -> Unit) {
    val context = LocalContext.current
    var section by remember { mutableStateOf(groups.first().id) }
    val preferences = controller.devicePreferences.values
    val state = controller.state
    fun openAccount(services: Boolean = false) {
        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://account.meoarch.org" + if(services) "/settings/services" else "")))
    }
    BackHandler(onBack = onClose)
    Scaffold(contentWindowInsets = WindowInsets.safeDrawing, topBar = {
        TopAppBar(title = { Text(stringResource(R.string.meo_settings_title)) }, navigationIcon = {
            IconButton(onClick = onClose) { Icon(Icons.Rounded.ArrowBack, stringResource(R.string.meo_settings_back)) }
        })
    }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                groups.forEach { group ->
                    FilterChip(selected = section == group.id, onClick = { section = group.id }, label = { Text(stringResource(labelResource(group.id))) })
                }
            }
            HorizontalDivider()
            LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(24.dp), verticalArrangement = Arrangement.spacedBy(22.dp)) {
                item { Text(stringResource(labelResource(section)), style = MaterialTheme.typography.headlineSmall) }
                when(section) {
                    "general" -> {
                        groups.first { it.id == "general" }.fields.forEach { field -> item(key = field) {
                            when(field) {
                                "enter_to_send" -> SettingsToggle(stringResource(R.string.meo_settings_enter), stringResource(R.string.meo_settings_enter_hint), preferences.enterToSend) {
                                    controller.devicePreferences.update(preferences.copy(enterToSend = it))
                                }
                                "theme" -> Column {
                                    Text(stringResource(R.string.meo_settings_theme), style = MaterialTheme.typography.titleMedium)
                                    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                        listOf("system" to R.string.meo_settings_system, "light" to R.string.meo_settings_light, "dark" to R.string.meo_settings_dark).forEach { (id, resource) ->
                                            FilterChip(selected = preferences.theme == id, onClick = { controller.devicePreferences.update(preferences.copy(theme = id)) }, label = { Text(stringResource(resource)) })
                                        }
                                    }
                                }
                                "reduce_motion" -> SettingsToggle(stringResource(R.string.meo_settings_motion), stringResource(R.string.meo_settings_motion_hint), preferences.reduceMotion) {
                                    controller.devicePreferences.update(preferences.copy(reduceMotion = it))
                                }
                            }
                        } }
                        item { Text(stringResource(R.string.meo_settings_device_scope), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                    }
                    "models" -> {
                        state.credentials.forEach { connection -> item(key = connection.id) {
                            Column { Text(connection.displayName.ifBlank { connection.provider }, style = MaterialTheme.typography.titleMedium); Text(connection.defaultModel, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                        } }
                        item { Text(stringResource(R.string.meo_settings_connections_hint)); TextButton(onClick = { openAccount(true) }) { Text(stringResource(R.string.meo_settings_open_account)) } }
                    }
                    "account" -> {
                        item { Text(state.email, style = MaterialTheme.typography.titleMedium) }
                        item { TextButton(onClick = { openAccount() }) { Text(stringResource(R.string.meo_settings_open_account)) } }
                        item { OutlinedButton(onClick = { controller.signOut(); onClose() }, enabled = !state.streaming) { Text(stringResource(R.string.meo_settings_sign_out)) } }
                    }
                    "privacy" -> {
                        item { Text(stringResource(R.string.meo_settings_privacy_hint)); TextButton(onClick = { openAccount() }) { Text(stringResource(R.string.meo_settings_open_account)) } }
                    }
                    else -> item {
                        Text(stringResource(when(section) {
                            "personalization" -> R.string.meo_settings_personalization_unavailable
                            "connectors" -> R.string.meo_settings_connectors_unavailable
                            "devices" -> R.string.meo_settings_devices_unavailable
                            else -> R.string.meo_settings_usage_unavailable
                        }), color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

@Composable
private fun SettingsToggle(label: String, description: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        Column(Modifier.weight(1f)) { Text(label, style = MaterialTheme.typography.titleMedium); Text(description, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        Switch(checked = checked, onCheckedChange = onChange, modifier = Modifier.semantics { contentDescription = label })
    }
}

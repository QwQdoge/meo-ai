package org.meo.ai.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Menu
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import org.json.JSONObject
import org.meo.ai.MeoController
import org.meo.ai.R
import org.meo.ai.schema.MeoUiSchema

private data class Destination(val id: String, val label: String, val placement: String, val order: Int)
private val destinations by lazy {
    val rows = JSONObject(MeoUiSchema.json).getJSONObject("navigation").getJSONArray("navigation")
    List(rows.length()) { rows.getJSONObject(it).let { row -> Destination(row.getString("id"),row.getString("label"),row.getString("placement"),row.getInt("order")) } }
        .sortedWith(compareBy<Destination> { it.order }.thenBy { it.id })
}

/** Native navigation layout; only schema controls entry placement and order. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProductWorkspace(controller: MeoController, chat: @Composable (openNavigation: () -> Unit, openSettings: () -> Unit) -> Unit) {
    var selected by rememberSaveable { mutableStateOf("chat") }
    val drawer = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    val savedScreens = rememberSaveableStateHolder()
    val openNavigation = { scope.launch { drawer.open() }; Unit }
    BackHandler(enabled = selected != "chat") { selected = "chat" }
    ModalNavigationDrawer(drawerState = drawer, drawerContent = {
        ModalDrawerSheet {
            Text("Meo AI", modifier = Modifier.padding(24.dp), style = MaterialTheme.typography.titleLarge)
            destinations.filter { it.placement == "primary" }.forEach { entry ->
                NavigationDrawerItem(label = { Text(if(entry.id=="settings") stringResource(R.string.meo_settings_title) else entry.label) }, selected = selected==entry.id,
                    onClick = { selected=entry.id;scope.launch { drawer.close() } }, modifier = Modifier.padding(horizontal=12.dp))
            }
            Spacer(Modifier.weight(1f))
            destinations.filter { it.placement == "secondary" }.forEach { entry ->
                NavigationDrawerItem(label = { Text(if(entry.id=="settings") stringResource(R.string.meo_settings_title) else entry.label) }, selected = selected==entry.id,
                    onClick = { selected=entry.id;scope.launch { drawer.close() } }, modifier = Modifier.padding(horizontal=12.dp))
            }
            Spacer(Modifier.height(24.dp))
        }
    }) {
        savedScreens.SaveableStateProvider(selected) {
            when(selected) {
                "chat" -> chat(openNavigation) { selected="settings" }
                "settings" -> SettingsScreen(controller) { selected="chat" }
                "work" -> WorkRunsScreen(controller, openNavigation)
                "projects" -> ProjectsScreen(controller, openNavigation)
                else -> Scaffold(contentWindowInsets=WindowInsets.safeDrawing, topBar={
                    TopAppBar(title={Text(destinations.first { it.id==selected }.label)},navigationIcon={
                        IconButton(onClick=openNavigation) { Icon(Icons.Rounded.Menu,stringResource(R.string.meo_navigation_title)) }
                    })
                }) { padding ->
                    Column(Modifier.fillMaxSize().padding(padding).padding(24.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
                        Text(stringResource(R.string.meo_workspace_unavailable),color=MaterialTheme.colorScheme.onSurfaceVariant)
                        TextButton(onClick={selected="chat"}) { Text(stringResource(R.string.meo_return_chat)) }
                    }
                }
            }
        }
    }
}

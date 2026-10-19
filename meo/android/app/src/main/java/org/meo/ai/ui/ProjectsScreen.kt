package org.meo.ai.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Menu
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import org.meo.ai.MeoController
import org.meo.ai.R

/** Account-scoped projects. Device-local desktop projects are not silently merged. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProjectsScreen(controller: MeoController, openNavigation: () -> Unit) {
    val state = controller.state
    var creating by rememberSaveable { mutableStateOf(false) }
    var newName by rememberSaveable { mutableStateOf("") }
    var renamingId by rememberSaveable { mutableStateOf("") }
    var editName by rememberSaveable { mutableStateOf("") }
    LaunchedEffect(Unit) { controller.loadProjects() }

    Scaffold(contentWindowInsets = WindowInsets.safeDrawing, topBar = {
        TopAppBar(
            title = { Text(stringResource(R.string.meo_projects_title)) },
            navigationIcon = {
                IconButton(onClick = openNavigation) {
                    Icon(Icons.Rounded.Menu, stringResource(R.string.meo_navigation_title))
                }
            },
            actions = {
                TextButton(onClick = { controller.loadProjects() }, enabled = !state.projectsBusy) {
                    Text(stringResource(R.string.meo_projects_refresh))
                }
            },
        )
    }) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Text(stringResource(R.string.meo_projects_cloud_scope),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            item {
                Button(onClick = { creating = !creating }, enabled = !state.projectsBusy) {
                    Text(if (creating) stringResource(R.string.meo_projects_cancel) else stringResource(R.string.meo_projects_new))
                }
            }
            if (creating) item {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedTextField(
                        value = newName, onValueChange = { if (it.length <= 160) newName = it },
                        label = { Text(stringResource(R.string.meo_projects_name)) },
                        singleLine = true, enabled = !state.projectsBusy,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Button(
                        enabled = !state.projectsBusy && newName.trim().isNotEmpty(),
                        onClick = {
                            controller.createProject(newName.trim())
                            creating = false
                            newName = ""
                        },
                    ) { Text(stringResource(R.string.meo_projects_create)) }
                }
            }
            if (state.projectsBusy) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
            state.projectsError?.let { cause ->
                item {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(stringResource(R.string.meo_projects_unavailable) + ": " + cause,
                            color = MaterialTheme.colorScheme.error)
                        TextButton(onClick = { controller.loadProjects() }, enabled = !state.projectsBusy) {
                            Text(stringResource(R.string.meo_projects_retry))
                        }
                    }
                }
            }
            if (state.projects.isEmpty() && !state.projectsBusy && state.projectsError == null) {
                item { Text(stringResource(R.string.meo_projects_empty), color = MaterialTheme.colorScheme.onSurfaceVariant) }
            }
            items(state.projects, key = { it.id }) { project ->
                val selected = state.selectedProjectId == project.id
                Card(
                    onClick = { controller.selectProject(project.id); renamingId = "" },
                    colors = CardDefaults.cardColors(containerColor =
                        if (selected) MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.surfaceContainerLow),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(project.name, style = MaterialTheme.typography.titleMedium)
                        Text(project.description.ifBlank { stringResource(R.string.meo_projects_no_description) },
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                        if (selected) {
                            Text(stringResource(R.string.meo_projects_context_note),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                            if (renamingId == project.id) {
                                OutlinedTextField(
                                    value = editName, onValueChange = { if (it.length <= 160) editName = it },
                                    label = { Text(stringResource(R.string.meo_projects_name)) },
                                    singleLine = true, enabled = !state.projectsBusy,
                                    modifier = Modifier.fillMaxWidth(),
                                )
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Button(onClick = {
                                        controller.renameProject(project.id, editName.trim())
                                        renamingId = ""
                                    }, enabled = !state.projectsBusy && editName.trim().isNotEmpty()) {
                                        Text(stringResource(R.string.meo_projects_save))
                                    }
                                    TextButton(onClick = { renamingId = "" }) {
                                        Text(stringResource(R.string.meo_projects_cancel))
                                    }
                                }
                            } else {
                                TextButton(onClick = { editName = project.name; renamingId = project.id }) {
                                    Text(stringResource(R.string.meo_projects_rename))
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

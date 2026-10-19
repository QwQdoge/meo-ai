package org.meo.ai.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Menu
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import org.meo.ai.MeoController
import org.meo.ai.R

private fun statusResource(status: String) = when (status) {
    "queued" -> R.string.meo_work_state_queued
    "dispatching" -> R.string.meo_work_state_dispatching
    "running" -> R.string.meo_work_state_running
    "awaiting_approval" -> R.string.meo_work_state_awaiting_approval
    "cancel_requested" -> R.string.meo_work_state_cancel_requested
    "completed" -> R.string.meo_work_state_completed
    "cancelled" -> R.string.meo_work_state_cancelled
    "failed" -> R.string.meo_work_state_failed
    else -> R.string.meo_work_state_unknown
}

/** Native account-owned remote Work *viewer*. The Cloud runner and device
 * AgentService own execution. A listed task is never re-dispatched here.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WorkRunsScreen(controller: MeoController, openNavigation: () -> Unit) {
    val state = controller.state
    val configured = controller.hasRemoteAgentCloud()
    LaunchedEffect(configured) { if (configured) controller.loadRemoteAgentRuns() }

    Scaffold(contentWindowInsets = WindowInsets.safeDrawing, topBar = {
        TopAppBar(
            title = { Text(stringResource(R.string.meo_work_title)) },
            navigationIcon = {
                IconButton(onClick = openNavigation) {
                    Icon(Icons.Rounded.Menu, stringResource(R.string.meo_navigation_title))
                }
            },
            actions = {
                TextButton(onClick = { controller.loadRemoteAgentRuns() },
                    enabled = configured && !state.remoteAgentRunsBusy) {
                    Text(stringResource(R.string.meo_work_refresh))
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
                Text(stringResource(R.string.meo_work_cloud_notice),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (!configured) {
                item {
                    Text(stringResource(R.string.meo_work_not_configured),
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            } else {
                if (state.remoteAgentRunsBusy) {
                    item { LinearProgressIndicator(modifier = Modifier.fillMaxWidth()) }
                }
                state.remoteAgentRunsError?.let { cause ->
                    item {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(stringResource(R.string.meo_work_unavailable) + ": " + cause,
                                color = MaterialTheme.colorScheme.error)
                            TextButton(onClick = { controller.loadRemoteAgentRuns() },
                                enabled = !state.remoteAgentRunsBusy) {
                                Text(stringResource(R.string.meo_work_retry))
                            }
                        }
                    }
                }
                if (state.remoteAgentRuns.isEmpty() && !state.remoteAgentRunsBusy &&
                    state.remoteAgentRunsError == null) {
                    item { Text(stringResource(R.string.meo_work_empty),
                        color = MaterialTheme.colorScheme.onSurfaceVariant) }
                }
                items(state.remoteAgentRuns, key = { it.id }) { run ->
                    Card(colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
                        modifier = Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(stringResource(R.string.meo_work_task_id, run.id.takeLast(8)),
                                style = MaterialTheme.typography.titleMedium)
                            Text(stringResource(statusResource(run.status)),
                                style = MaterialTheme.typography.bodyMedium)
                            Text(stringResource(R.string.meo_work_device, run.deviceId),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
                item {
                    Text(stringResource(R.string.meo_work_viewer_only),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

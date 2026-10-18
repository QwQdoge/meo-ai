package org.meo.ai.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import org.meo.ai.CloudMemory
import org.meo.ai.MeoController

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PersonalizationScreen(controller: MeoController, onBack: () -> Unit) {
    val state = controller.state
    val settings = state.cloudSettings
    var instructions by remember(settings?.version) {
        mutableStateOf(settings?.personalInstructions.orEmpty())
    }
    var memoryEnabled by remember(settings?.version) {
        mutableStateOf(settings?.memoryEnabled ?: true)
    }
    var newMemory by remember { mutableStateOf("") }
    var editing by remember { mutableStateOf<CloudMemory?>(null) }
    var deleting by remember { mutableStateOf<CloudMemory?>(null) }

    BackHandler(onBack = onBack)
    LaunchedEffect(Unit) { controller.loadPersonalization() }
    // Retain typed content on failure; clear only after the server accepted it.
    LaunchedEffect(state.memoryCreatedSerial) {
        if (state.memoryCreatedSerial > 0) newMemory = ""
    }

    editing?.let { item ->
        var content by remember(item.id) { mutableStateOf(item.content) }
        AlertDialog(
            onDismissRequest = { editing = null },
            title = { Text("Edit memory") },
            text = {
                OutlinedTextField(
                    value = content,
                    onValueChange = { if (it.length <= 2000) content = it },
                    label = { Text("Memory") },
                    minLines = 2,
                )
            },
            confirmButton = {
                TextButton(
                    enabled = content.isNotBlank() && !state.personalizationBusy,
                    onClick = {
                        controller.changePersonalMemory(item, content = content.trim())
                        editing = null
                    },
                ) { Text("Save") }
            },
            dismissButton = {
                TextButton(onClick = { editing = null }) { Text("Cancel") }
            },
        )
    }
    deleting?.let { item ->
        AlertDialog(
            onDismissRequest = { deleting = null },
            title = { Text("Delete this memory?") },
            text = { Text("This permanently deletes the saved item.") },
            confirmButton = {
                TextButton(
                    enabled = !state.personalizationBusy,
                    onClick = { controller.deletePersonalMemory(item); deleting = null },
                ) { Text("Delete") }
            },
            dismissButton = { TextButton(onClick = { deleting = null }) { Text("Cancel") } },
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Personalization") },
                navigationIcon = {
                    TextButton(onClick = onBack) { Text("Back") }
                },
                actions = {
                    TextButton(
                        enabled = !state.personalizationBusy,
                        onClick = { controller.loadPersonalization(state.archivedMemories) },
                    ) { Text("Refresh") }
                },
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            verticalArrangement = Arrangement.spacedBy(16.dp),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(20.dp),
        ) {
            if (state.personalizationError != null) {
                item {
                    Text(
                        state.personalizationError,
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
            if (settings == null) {
                item {
                    if (state.personalizationBusy) {
                        CircularProgressIndicator()
                    } else {
                        Button(onClick = { controller.loadPersonalization() }) { Text("Load settings") }
                    }
                }
            } else {
                item {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("Personal instructions", style = MaterialTheme.typography.titleMedium)
                        Text(
                            "Used in new model requests. Never store passwords or API keys here.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        OutlinedTextField(
                            value = instructions,
                            onValueChange = { if (it.length <= 5000) instructions = it },
                            modifier = Modifier.fillMaxWidth(),
                            minLines = 4,
                            label = { Text("How should Meo AI respond?") },
                        )
                        Text("${instructions.length} / 5000", style = MaterialTheme.typography.labelSmall)
                    }
                }
                item {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text("Use saved memories", fontWeight = FontWeight.Medium)
                            Text(
                                "Disabled and archived memories are excluded from model context.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        Switch(
                            checked = memoryEnabled,
                            onCheckedChange = { memoryEnabled = it },
                            enabled = !state.personalizationBusy,
                        )
                    }
                }
                item {
                    Button(
                        enabled = !state.personalizationBusy &&
                            (instructions != settings.personalInstructions ||
                                memoryEnabled != settings.memoryEnabled),
                        onClick = { controller.savePersonalization(instructions, memoryEnabled) },
                    ) { Text("Save account settings") }
                }
                item {
                    HorizontalDivider()
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            if (state.archivedMemories) "Archived memories" else "Saved memories",
                            style = MaterialTheme.typography.titleMedium,
                        )
                        TextButton(
                            enabled = !state.personalizationBusy,
                            onClick = { controller.loadPersonalization(!state.archivedMemories) },
                        ) { Text(if (state.archivedMemories) "Active" else "Archived") }
                    }
                }
                if (!state.archivedMemories) {
                    item {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedTextField(
                                value = newMemory,
                                onValueChange = { if (it.length <= 2000) newMemory = it },
                                enabled = !state.personalizationBusy,
                                modifier = Modifier.fillMaxWidth(),
                                label = { Text("Add a memory") },
                                minLines = 2,
                            )
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Button(
                                    enabled = !state.personalizationBusy && newMemory.isNotBlank(),
                                    onClick = { controller.addPersonalMemory(newMemory.trim()) },
                                ) { Text("Add memory") }
                                if (state.personalizationBusy) {
                                    Spacer(Modifier.padding(8.dp))
                                    CircularProgressIndicator(strokeWidth = 2.dp)
                                }
                            }
                        }
                    }
                }
                if (state.cloudMemories.isEmpty()) {
                    item {
                        Text(
                            if (state.archivedMemories) "No archived memories."
                            else "No saved memories yet.",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                items(state.cloudMemories, key = { it.id }) { item ->
                    Card {
                        Column(
                            modifier = Modifier.fillMaxWidth().padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            Text(
                                "${item.kind}${if (!item.enabled) " · disabled" else ""}",
                                style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            Text(item.content, style = MaterialTheme.typography.bodyMedium)
                            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                TextButton(
                                    enabled = !state.personalizationBusy,
                                    onClick = { editing = item },
                                ) { Text("Edit") }
                                if (!state.archivedMemories) {
                                    TextButton(
                                        enabled = !state.personalizationBusy,
                                        onClick = { controller.changePersonalMemory(item, enabled = !item.enabled) },
                                    ) { Text(if (item.enabled) "Disable" else "Enable") }
                                }
                                TextButton(
                                    enabled = !state.personalizationBusy,
                                    onClick = {
                                        controller.changePersonalMemory(
                                            item, archived = !state.archivedMemories,
                                        )
                                    },
                                ) { Text(if (state.archivedMemories) "Restore" else "Archive") }
                                TextButton(
                                    enabled = !state.personalizationBusy,
                                    onClick = { deleting = item },
                                ) { Text("Delete") }
                            }
                        }
                    }
                }
            }
        }
    }
}

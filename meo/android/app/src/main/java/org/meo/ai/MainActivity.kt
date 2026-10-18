package org.meo.ai

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.weight
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AccountCircle
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.ExpandMore
import androidx.compose.material.icons.rounded.History
import androidx.compose.material.icons.rounded.Login
import androidx.compose.material.icons.rounded.Logout
import androidx.compose.material.icons.rounded.Menu
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Send
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.FilledTonalIconButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.type
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import org.meo.ai.core.MeoCore
import org.meo.ai.model.AiModel
import org.meo.ai.model.ConsentPreview
import org.meo.ai.model.Credential
import org.meo.ai.model.UiMessage
import org.meo.ai.ui.MeoExpressiveTheme
import org.meo.ai.ui.RichBlockRenderer
import java.net.URI

class MainActivity : ComponentActivity() {
    private lateinit var controller: MeoController

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        controller = MeoController(this)
        controller.handleOAuthCallback(intent?.data)
        enableEdgeToEdge()
        setContent {
            MeoExpressiveTheme(themeMode = controller.devicePreferences.values.theme, reduceMotion = controller.devicePreferences.values.reduceMotion) {
                MeoApp(controller)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        controller.handleOAuthCallback(intent.data)
    }

    override fun onDestroy() {
        if (isFinishing) controller.close()
        super.onDestroy()
    }
}

@Composable
private fun MeoApp(controller: MeoController) {
    val state = controller.state
    val snackbar = remember { SnackbarHostState() }
    LaunchedEffect(state.error) {
        val message = state.error ?: return@LaunchedEffect
        snackbar.showSnackbar(message)
        controller.clearError()
    }

    if (!state.signedIn) {
        SignInScreen(
            loading = state.loading,
            configured = BuildConfig.MEO_OAUTH_CLIENT_ID.isNotBlank(),
            snackbar = snackbar,
            onSignIn = controller::signIn,
        )
        return
    }

    org.meo.ai.ui.ProductWorkspace(controller) { openNavigation, openSettings -> ChatScreen(controller, snackbar, openNavigation, openSettings) }
}

@Composable
private fun SignInScreen(
    loading: Boolean,
    configured: Boolean,
    snackbar: SnackbarHostState,
    onSignIn: () -> Unit,
) {
    Scaffold(
        contentWindowInsets = WindowInsets.safeDrawing,
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        Box(
            modifier = Modifier.fillMaxSize().padding(padding).padding(24.dp),
            contentAlignment = Alignment.Center,
        ) {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = MaterialTheme.shapes.extraLargeIncreased,
                color = MaterialTheme.colorScheme.surfaceContainer,
                tonalElevation = 1.dp,
            ) {
                Column(
                    modifier = Modifier.padding(28.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(18.dp),
                ) {
                    Surface(
                        modifier = Modifier.size(68.dp),
                        shape = RoundedCornerShape(24.dp),
                        color = MaterialTheme.colorScheme.primaryContainer,
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Icon(
                                Icons.Rounded.AutoAwesome,
                                contentDescription = null,
                                modifier = Modifier.size(34.dp),
                                tint = MaterialTheme.colorScheme.onPrimaryContainer,
                            )
                        }
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            "Meo AI",
                            style = MaterialTheme.typography.headlineLarge,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(
                            "Use your Meo Account to access conversations and provider connections.",
                            modifier = Modifier.padding(top = 8.dp),
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Button(onClick = onSignIn, enabled = configured && !loading) {
                        if (loading) {
                            CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                        } else {
                            Icon(Icons.Rounded.Login, contentDescription = null)
                        }
                        Spacer(Modifier.size(8.dp))
                        Text("Continue with Meo Account")
                    }
                    if (!configured) {
                        Text(
                            "This build needs the public Android OAuth client ID before sign-in can be enabled.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error,
                        )
                    }
                    Text(
                        if (MeoCore.available) "Native Compose · shared Rust rich-content core" else "Native Compose · Rust core unavailable in this build",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ChatScreen(controller: MeoController, snackbar: SnackbarHostState, openNavigation: () -> Unit, openSettings: () -> Unit) {
    val state = controller.state
    val listState = rememberLazyListState()
    val topBarScroll = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    var composer by rememberSaveable { mutableStateOf("") }
    var historyOpen by remember { mutableStateOf(false) }
    var accountOpen by remember { mutableStateOf(false) }


    LaunchedEffect(state.messages.size, state.messages.lastOrNull()?.text) {
        if (state.messages.isNotEmpty()) {
            if (controller.devicePreferences.values.reduceMotion) listState.scrollToItem(state.messages.lastIndex)
            else listState.animateScrollToItem(state.messages.lastIndex)
        }
    }

    state.pendingSend?.let { pending ->
        ConsentDialog(
            consent = pending.consent,
            onConfirm = controller::confirmPendingSend,
            onDismiss = controller::cancelPendingSend,
        )
    }

    Scaffold(
        modifier = Modifier.nestedScroll(topBarScroll.nestedScrollConnection),
        contentWindowInsets = WindowInsets.safeDrawing,
        containerColor = MaterialTheme.colorScheme.surface,
        snackbarHost = { SnackbarHost(snackbar) },
        topBar = {
            LargeTopAppBar(
                title = {
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(
                            state.conversations.firstOrNull { it.id == state.currentConversationId }?.title ?: "Meo AI",
                            style = MaterialTheme.typography.headlineMedium,
                            fontWeight = FontWeight.SemiBold,
                            maxLines = 1,
                        )
                        Text(
                            statusLine(state.credentials, state.selectedCredentialId, state.selectedModelId),
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 1,
                        )
                    }
                },
                navigationIcon = {
                    IconButton(onClick = openNavigation) {
                        Icon(Icons.Rounded.Menu, contentDescription = androidx.compose.ui.res.stringResource(org.meo.ai.R.string.meo_navigation_title))
                    }
                },
                actions = {
                    Box {
                        FilledTonalIconButton(onClick = { historyOpen = true }) {
                            Icon(Icons.Rounded.History, contentDescription = "Conversation history")
                        }
                        DropdownMenu(expanded = historyOpen, onDismissRequest = { historyOpen = false }) {
                            DropdownMenuItem(
                                text = { Text("New chat") },
                                leadingIcon = { Icon(Icons.Rounded.Add, contentDescription = null) },
                                onClick = {
                                    historyOpen = false
                                    controller.newChat()
                                },
                            )
                            if (state.conversations.isNotEmpty()) HorizontalDivider()
                            state.conversations.take(30).forEach { conversation ->
                                DropdownMenuItem(
                                    text = { Text(conversation.title, maxLines = 1) },
                                    leadingIcon = { Icon(Icons.Rounded.History, contentDescription = null) },
                                    trailingIcon = if (conversation.id == state.currentConversationId) {
                                        { Icon(Icons.Rounded.Check, contentDescription = "Current conversation") }
                                    } else null,
                                    onClick = {
                                        historyOpen = false
                                        controller.openConversation(conversation.id)
                                    },
                                )
                            }
                        }
                    }
                    IconButton(onClick = controller::newChat, enabled = !state.streaming) {
                        Icon(Icons.Rounded.Add, contentDescription = "New chat")
                    }
                    Box {
                        FilledTonalIconButton(onClick = { accountOpen = true }) {
                            Icon(Icons.Rounded.AccountCircle, contentDescription = "Meo Account")
                        }
                        DropdownMenu(expanded = accountOpen, onDismissRequest = { accountOpen = false }) {
                            DropdownMenuItem(
                                text = {
                                    Column {
                                        Text("Meo Account", fontWeight = FontWeight.SemiBold)
                                        if (state.email.isNotBlank()) {
                                            Text(
                                                state.email,
                                                style = MaterialTheme.typography.bodySmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                            )
                                        }
                                    }
                                },
                                onClick = { accountOpen = false },
                            )
                            DropdownMenuItem(
                                text = { Text(androidx.compose.ui.res.stringResource(org.meo.ai.R.string.meo_settings_title)) },
                                onClick = { accountOpen = false; openSettings() },
                            )
                            HorizontalDivider()
                            DropdownMenuItem(
                                text = { Text("Sign out") },
                                leadingIcon = { Icon(Icons.Rounded.Logout, contentDescription = null) },
                                onClick = {
                                    accountOpen = false
                                    controller.signOut()
                                },
                            )
                        }
                    }
                },
                scrollBehavior = topBarScroll,
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                    scrolledContainerColor = MaterialTheme.colorScheme.surfaceContainer,
                ),
            )
        },
        bottomBar = {
            Column {
                ConnectionModelBar(
                    credentials = state.credentials,
                    selectedCredentialId = state.selectedCredentialId,
                    models = state.models,
                    selectedModelId = state.selectedModelId,
                    enabled = !state.streaming && !state.loading,
                    onCredential = controller::selectCredential,
                    onModel = controller::selectModel,
                )
                Composer(
                    enterToSend = controller.devicePreferences.values.enterToSend,
                    value = composer,
                    onValueChange = { composer = it },
                    sending = state.streaming || state.loading,
                    enabled = state.selectedCredentialId != null && state.selectedModelId != null,
                    onSend = {
                        val text = composer.trim()
                        if (text.isNotEmpty()) {
                            controller.beginSend(text)
                            composer = ""
                        }
                    },
                )
            }
        },
    ) { padding ->
        if (state.messages.isEmpty()) {
            EmptyConversation(
                modifier = Modifier.fillMaxSize().padding(padding),
                hasCredential = state.credentials.isNotEmpty(),
                loading = state.loading,
            )
        } else {
            LazyColumn(
                state = listState,
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 28.dp),
                verticalArrangement = Arrangement.spacedBy(22.dp),
            ) {
                items(state.messages, key = { it.id }) { message ->
                    MessageRow(message)
                }
                if (state.streaming) {
                    item("streaming") {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(start = 44.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp)
                            Text(
                                "Meo is responding…",
                                style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun EmptyConversation(modifier: Modifier, hasCredential: Boolean, loading: Boolean) {
    Box(modifier = modifier.padding(24.dp), contentAlignment = Alignment.Center) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Surface(
                modifier = Modifier.size(56.dp),
                shape = RoundedCornerShape(20.dp),
                color = MaterialTheme.colorScheme.primaryContainer,
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(Icons.Rounded.AutoAwesome, contentDescription = null)
                }
            }
            Text("What can I help with?", style = MaterialTheme.typography.headlineSmall)
            Text(
                if (hasCredential) "Pick a model below, then start a conversation."
                else "Add an AI connection in Meo Account, then reopen or refresh this app.",
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (loading) CircularProgressIndicator(modifier = Modifier.size(22.dp), strokeWidth = 2.dp)
        }
    }
}

@Composable
private fun ConnectionModelBar(
    credentials: List<Credential>,
    selectedCredentialId: String?,
    models: List<AiModel>,
    selectedModelId: String?,
    enabled: Boolean,
    onCredential: (String) -> Unit,
    onModel: (String) -> Unit,
) {
    var connectionOpen by remember { mutableStateOf(false) }
    var modelOpen by remember { mutableStateOf(false) }
    val credential = credentials.firstOrNull { it.id == selectedCredentialId }
    val model = models.firstOrNull { it.id == selectedModelId }

    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 2.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Box {
            AssistChip(
                onClick = { if (enabled) connectionOpen = true },
                enabled = enabled && credentials.isNotEmpty(),
                label = { Text(credential?.displayName ?: "AI connection", maxLines = 1) },
                trailingIcon = { Icon(Icons.Rounded.ExpandMore, contentDescription = null) },
            )
            DropdownMenu(expanded = connectionOpen, onDismissRequest = { connectionOpen = false }) {
                credentials.forEach { item ->
                    DropdownMenuItem(
                        text = {
                            Column {
                                Text(item.displayName)
                                Text(
                                    item.provider,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        },
                        trailingIcon = if (item.id == selectedCredentialId) {
                            { Icon(Icons.Rounded.Check, contentDescription = null) }
                        } else null,
                        onClick = {
                            connectionOpen = false
                            onCredential(item.id)
                        },
                    )
                }
            }
        }
        Box {
            AssistChip(
                onClick = { if (enabled && models.isNotEmpty()) modelOpen = true },
                enabled = enabled && selectedModelId != null,
                label = { Text(model?.name ?: selectedModelId ?: "Model", maxLines = 1) },
                trailingIcon = { Icon(Icons.Rounded.ExpandMore, contentDescription = null) },
            )
            DropdownMenu(expanded = modelOpen, onDismissRequest = { modelOpen = false }) {
                models.take(100).forEach { item ->
                    DropdownMenuItem(
                        text = {
                            Column {
                                Text(item.name, maxLines = 1)
                                if (item.description.isNotBlank()) {
                                    Text(
                                        item.description,
                                        maxLines = 2,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                            }
                        },
                        trailingIcon = if (item.id == selectedModelId) {
                            { Icon(Icons.Rounded.Check, contentDescription = null) }
                        } else null,
                        onClick = {
                            modelOpen = false
                            onModel(item.id)
                        },
                    )
                }
            }
        }
    }
}

@Composable
private fun ConsentDialog(
    consent: ConsentPreview,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
) {
    val host = remember(consent.destination) {
        runCatching { URI(consent.destination).host }.getOrNull().orEmpty()
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        icon = { Icon(Icons.Rounded.AutoAwesome, contentDescription = null) },
        title = { Text("Send to ${consent.providerName}") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Model: ${consent.model}")
                if (host.isNotBlank()) Text("Destination: $host")
                Text(
                    "Your message and recent conversation context will be sent to this AI provider for this reply. This approval is single-use and expires shortly.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        },
        confirmButton = {
            Button(onClick = onConfirm) {
                Icon(Icons.Rounded.Send, contentDescription = null)
                Spacer(Modifier.size(8.dp))
                Text("Send")
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun MessageRow(message: UiMessage) {
    if (message.role == "user") {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            Card(
                modifier = Modifier.fillMaxWidth(0.88f),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer),
                shape = MaterialTheme.shapes.largeIncreased,
                elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
            ) {
                Text(
                    message.text,
                    modifier = Modifier.padding(horizontal = 18.dp, vertical = 14.dp),
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSecondaryContainer,
                )
            }
        }
        return
    }

    Column(
        modifier = Modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Surface(
                modifier = Modifier.size(34.dp),
                shape = RoundedCornerShape(12.dp),
                color = MaterialTheme.colorScheme.primaryContainer,
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(
                        Icons.Rounded.AutoAwesome,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onPrimaryContainer,
                        modifier = Modifier.size(18.dp),
                    )
                }
            }
            Text(
                "Meo",
                style = MaterialTheme.typography.titleSmall,
                color = MaterialTheme.colorScheme.onSurface,
                fontWeight = FontWeight.SemiBold,
            )
        }
        if (message.blocksJson != "[]") {
            RichBlockRenderer(
                blocksJson = if (MeoCore.available) {
                    runCatching { MeoCore.normalizeBlocks(message.blocksJson) }.getOrDefault(message.blocksJson)
                } else {
                    message.blocksJson
                },
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Composable
private fun Composer(
    enterToSend: Boolean,
    value: String,
    onValueChange: (String) -> Unit,
    sending: Boolean,
    enabled: Boolean,
    onSend: () -> Unit,
) {
    var fieldValue by remember { mutableStateOf(TextFieldValue(value)) }
    LaunchedEffect(value) { if (fieldValue.text != value) fieldValue = TextFieldValue(value) }
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .navigationBarsPadding()
            .imePadding()
            .padding(horizontal = 10.dp, vertical = 8.dp),
        shape = MaterialTheme.shapes.extraLargeIncreased,
        color = MaterialTheme.colorScheme.surfaceContainerHigh,
        tonalElevation = 2.dp,
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            OutlinedTextField(
                value = fieldValue,
                onValueChange = { fieldValue = it; onValueChange(it.text) },
                enabled = !sending,
                modifier = Modifier.fillMaxWidth().onPreviewKeyEvent { event ->
                    val native = event.nativeKeyEvent
                    val modified = native.isCtrlPressed || native.isMetaPressed
                    val shouldSend = if (enterToSend) !modified else modified
                    if (event.type == KeyEventType.KeyDown && native.keyCode == android.view.KeyEvent.KEYCODE_ENTER &&
                        !native.isShiftPressed && fieldValue.composition == null && shouldSend) {
                        if (enabled && !sending && value.isNotBlank()) onSend()
                        true
                    } else false
                },
                placeholder = { Text(if (enabled) "Ask anything" else "Select an AI connection and model") },
                maxLines = 7,
                shape = MaterialTheme.shapes.extraLarge,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = { if (enabled && !sending) onSend() }),
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "Single-use provider consent · synced with Meo Account",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.weight(1f).padding(start = 6.dp),
                )
                FilledIconButton(
                    onClick = onSend,
                    enabled = enabled && value.isNotBlank() && !sending,
                ) {
                    if (sending) {
                        CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                    } else {
                        Icon(Icons.Rounded.Send, contentDescription = "Send")
                    }
                }
            }
        }
    }
}

private fun statusLine(
    credentials: List<Credential>,
    selectedCredentialId: String?,
    selectedModelId: String?,
): String {
    val connection = credentials.firstOrNull { it.id == selectedCredentialId }?.displayName ?: "No AI connection"
    val model = selectedModelId ?: "No model"
    return "$connection · $model · ${if (MeoCore.available) "native rich UI" else "Android"}"
}

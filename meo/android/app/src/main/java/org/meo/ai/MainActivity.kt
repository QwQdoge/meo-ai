package org.meo.ai

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
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
import androidx.compose.material.icons.rounded.AttachFile
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.Menu
import androidx.compose.material.icons.rounded.MoreVert
import androidx.compose.material.icons.rounded.Send
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
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
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import org.meo.ai.core.MeoCore
import org.meo.ai.ui.MeoExpressiveTheme
import org.meo.ai.ui.RichBlockRenderer

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { MeoExpressiveTheme { MeoApp() } }
    }
}

data class UiMessage(
    val role: String,
    val text: String = "",
    val blocksJson: String = "[]",
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MeoApp() {
    val normalizedDemo = remember {
        if (MeoCore.available) {
            runCatching { MeoCore.normalizeBlocks(DEMO_BLOCKS) }.getOrDefault(DEMO_BLOCKS)
        } else {
            DEMO_BLOCKS
        }
    }
    val messages = remember {
        mutableStateListOf(
            UiMessage(role = "assistant", blocksJson = normalizedDemo),
        )
    }
    var composer by remember { mutableStateOf("") }
    val listState = rememberLazyListState()
    val topBarScroll = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()

    fun send() {
        val text = composer.trim()
        if (text.isEmpty()) return
        messages += UiMessage(role = "user", text = text)
        messages += UiMessage(
            role = "assistant",
            blocksJson = """[
                {"type":"markdown","block_id":"local:reply","text":"**Meo AI Android is using the shared Rust core.** This UI is native Compose and follows Material 3 Expressive rather than wrapping the web client."},
                {"type":"tool_activity","block_id":"local:rust","activity_id":"rust:core","title":"Rust core","state":"completed","detail":"Protocol, rich blocks and streaming normalization are shared with the other Meo AI clients.","source":"android"}
            ]""".trimIndent(),
        )
        composer = ""
    }

    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.lastIndex)
    }

    Scaffold(
        modifier = Modifier.nestedScroll(topBarScroll.nestedScrollConnection),
        contentWindowInsets = WindowInsets.safeDrawing,
        containerColor = MaterialTheme.colorScheme.surface,
        topBar = {
            LargeTopAppBar(
                title = {
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(
                            "Meo AI",
                            style = MaterialTheme.typography.headlineMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(
                            if (MeoCore.available) "Rust core · connected" else "Rust core · unavailable",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                },
                navigationIcon = {
                    FilledTonalIconButton(onClick = {}) {
                        Icon(Icons.Rounded.Menu, contentDescription = "Open navigation")
                    }
                },
                actions = {
                    IconButton(onClick = {}) {
                        Icon(Icons.Rounded.Add, contentDescription = "New chat")
                    }
                    FilledTonalIconButton(onClick = {}) {
                        Icon(Icons.Rounded.AccountCircle, contentDescription = "Meo Account")
                    }
                    IconButton(onClick = {}) {
                        Icon(Icons.Rounded.MoreVert, contentDescription = "More")
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
            Composer(
                value = composer,
                onValueChange = { composer = it },
                onSend = ::send,
            )
        },
    ) { padding ->
        LazyColumn(
            state = listState,
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 28.dp),
            verticalArrangement = Arrangement.spacedBy(22.dp),
        ) {
            items(messages) { message ->
                MessageRow(message)
            }
        }
    }
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
        RichBlockRenderer(
            blocksJson = message.blocksJson,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
private fun Composer(
    value: String,
    onValueChange: (String) -> Unit,
    onSend: () -> Unit,
) {
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
                value = value,
                onValueChange = onValueChange,
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("Ask anything") },
                maxLines = 7,
                shape = MaterialTheme.shapes.extraLarge,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = { onSend() }),
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                FilledTonalIconButton(onClick = {}) {
                    Icon(Icons.Rounded.AttachFile, contentDescription = "Attach")
                }
                Surface(
                    shape = RoundedCornerShape(999.dp),
                    color = MaterialTheme.colorScheme.surfaceContainerHighest,
                ) {
                    Text(
                        "Auto · Best model",
                        modifier = Modifier.padding(horizontal = 13.dp, vertical = 9.dp),
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Box(Modifier.weight(1f))
                FilledIconButton(
                    onClick = onSend,
                    enabled = value.isNotBlank(),
                ) {
                    Icon(Icons.Rounded.Send, contentDescription = "Send")
                }
            }
        }
    }
}

private val DEMO_BLOCKS = """
[
  {
    "type":"markdown",
    "block_id":"demo:intro",
    "text":"# One conversation, richer answers\nMeo AI renders **structured responses** without flattening tools, charts and artifacts into text."
  },
  {
    "type":"code",
    "block_id":"demo:code",
    "language":"rust",
    "filename":"service.rs",
    "text":"let request_id = service.send_message(conversation_id, input)?;\nlet stream = client.events(&request_id, 0).await?;"
  },
  {
    "type":"chart",
    "block_id":"demo:chart",
    "chart_id":"chart:usage",
    "kind":"bar",
    "title":"Example model usage",
    "x_key":"model",
    "series":[{"key":"tokens","label":"Tokens","unit":"tokens"}],
    "data":[{"model":"Fast","tokens":18},{"model":"Think","tokens":31},{"model":"Code","tokens":24}]
  },
  {
    "type":"table",
    "block_id":"demo:table",
    "table_id":"table:clients",
    "title":"One Rust core, native surfaces",
    "columns":[{"key":"client","label":"Client"},{"key":"ui","label":"Native UI"},{"key":"core","label":"Core"}],
    "rows":[{"client":"Desktop","ui":"QML + MeoUI","core":"Rust"},{"client":"Web","ui":"React","core":"Rust service"},{"client":"Android","ui":"Compose M3E","core":"Rust"}]
  },
  {
    "type":"plugin",
    "block_id":"demo:plugin",
    "presentation":{
      "plugin_id":"demo.connector",
      "plugin_name":"Example connector",
      "title":"Interactive plugin surface",
      "subtitle":"Connectors return structured UI instead of raw JSON.",
      "body":{"status":"ready"},
      "actions":[{"action_id":"open","label":"Open"}]
    }
  },
  {
    "type":"html",
    "block_id":"demo:html",
    "artifact_id":"artifact:preview",
    "title":"Sandboxed HTML artifact",
    "html":"<main style='font:16px system-ui;padding:20px'><h2>Meo Artifact</h2><p>This preview is isolated from native APIs.</p><button>Preview control</button></main>",
    "sandbox":"static"
  }
]
""".trimIndent()

package org.meo.ai

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import org.meo.ai.core.MeoCore
import org.meo.ai.ui.RichBlockRenderer

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { MeoTheme { MeoApp() } }
    }
}

data class UiMessage(
    val role: String,
    val text: String = "",
    val blocksJson: String = "[]",
)

@Composable
private fun MeoTheme(content: @Composable () -> Unit) {
    val context = LocalContext.current
    val dark = isSystemInDarkTheme()
    val scheme = remember(context, dark) {
        if (android.os.Build.VERSION.SDK_INT >= 31) {
            if (dark) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        } else {
            if (dark) darkColorScheme() else lightColorScheme()
        }
    }
    MaterialTheme(colorScheme = scheme, content = content)
}

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
            UiMessage(
                role = "assistant",
                blocksJson = normalizedDemo,
            ),
        )
    }
    var composer by remember { mutableStateOf("") }

    fun send() {
        val text = composer.trim()
        if (text.isEmpty()) return
        messages += UiMessage(role = "user", text = text)
        messages += UiMessage(
            role = "assistant",
            blocksJson = """[
                {"type":"markdown","block_id":"local:reply","text":"**Android client is ready.** The next transport step will stream this response from the same Meo AgentService used by desktop and web."},
                {"type":"tool_activity","block_id":"local:rust","activity_id":"rust:core","title":"Rust shared core","state":"completed","detail":"Rich blocks and SSE normalization are running through meo-ai-core.","source":"android"}
            ]""".trimIndent(),
        )
        composer = ""
    }

    Scaffold(
        contentWindowInsets = WindowInsets.safeDrawing,
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Meo AI", fontWeight = FontWeight.SemiBold)
                        Text(
                            if (MeoCore.available) "Rust core connected" else "Rust core unavailable",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
                actions = {
                    Surface(
                        modifier = Modifier.padding(end = 12.dp),
                        shape = RoundedCornerShape(999.dp),
                        color = MaterialTheme.colorScheme.secondaryContainer,
                    ) {
                        Text(
                            "Meo Account",
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp),
                            style = MaterialTheme.typography.labelMedium,
                        )
                    }
                },
            )
        },
        bottomBar = {
            Surface(
                tonalElevation = 2.dp,
                modifier = Modifier.navigationBarsPadding().imePadding(),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(12.dp),
                    verticalAlignment = Alignment.Bottom,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    OutlinedTextField(
                        value = composer,
                        onValueChange = { composer = it },
                        modifier = Modifier.weight(1f),
                        placeholder = { Text("Ask anything…") },
                        shape = RoundedCornerShape(24.dp),
                        maxLines = 6,
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                        keyboardActions = KeyboardActions(onSend = { send() }),
                    )
                    Button(onClick = { send() }, enabled = composer.isNotBlank()) {
                        Text("Send")
                    }
                }
            }
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(
                    start = 16.dp,
                    end = 16.dp,
                    top = 12.dp,
                    bottom = 24.dp,
                ),
                verticalArrangement = Arrangement.spacedBy(20.dp),
            ) {
                items(messages) { message ->
                    if (message.role == "user") {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                            Card(
                                colors = CardDefaults.cardColors(
                                    containerColor = MaterialTheme.colorScheme.secondaryContainer,
                                ),
                                shape = RoundedCornerShape(22.dp),
                            ) {
                                Text(
                                    message.text,
                                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
                                    style = MaterialTheme.typography.bodyLarge,
                                )
                            }
                        }
                    } else {
                        Column(
                            modifier = Modifier.fillMaxWidth(),
                            verticalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            Text(
                                "Meo",
                                style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.primary,
                                fontWeight = FontWeight.SemiBold,
                            )
                            RichBlockRenderer(
                                blocksJson = message.blocksJson,
                                modifier = Modifier.fillMaxWidth(),
                            )
                        }
                    }
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
    "text":"# One conversation, richer answers\nMeo AI can render **structured content** instead of flattening everything into plain Markdown."
  },
  {
    "type":"code",
    "block_id":"demo:code",
    "language":"rust",
    "filename":"stream.rs",
    "text":"let event = decode_sse_line(line)?;\nrender(event.blocks);"
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
    "title":"Shared capability surface",
    "columns":[{"key":"client","label":"Client"},{"key":"ui","label":"UI"},{"key":"core","label":"Core"}],
    "rows":[{"client":"Desktop","ui":"QML","core":"Rust"},{"client":"Web","ui":"React","core":"Protocol"},{"client":"Android","ui":"Compose","core":"Rust"}]
  },
  {
    "type":"plugin",
    "block_id":"demo:plugin",
    "presentation":{
      "plugin_id":"demo.weather",
      "plugin_name":"Example connector",
      "title":"Interactive plugin surface",
      "subtitle":"Connectors can return cards instead of dumping JSON into chat.",
      "body":{"status":"ready"},
      "actions":[{"action_id":"open","label":"Open"}]
    }
  },
  {
    "type":"html",
    "block_id":"demo:html",
    "artifact_id":"artifact:preview",
    "title":"Sandboxed HTML artifact",
    "html":"<main style='font:16px system-ui;padding:20px'><h2>Meo Artifact</h2><p>This HTML is isolated from native APIs.</p><button>Preview control</button></main>",
    "sandbox":"static"
  }
]
""".trimIndent()

package org.meo.ai.ui

import androidx.compose.material.icons.rounded.ViewSidebar
import androidx.compose.material.icons.rounded.Cable
import androidx.compose.material.icons.rounded.Terminal
import androidx.compose.material.icons.rounded.Build
import androidx.compose.material.icons.rounded.Bolt
import androidx.compose.material.icons.rounded.EditNote
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.ExpandLess
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.ui.graphics.graphicsLayer
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import coil3.compose.AsyncImage
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.unit.IntOffset
import androidx.compose.material.icons.rounded.AccountTree
import androidx.compose.material.icons.rounded.ExpandMore
import androidx.compose.material.icons.rounded.ArrowDownward
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.animation.core.animateFloat
import androidx.compose.material.icons.rounded.Cloud
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.Edit
import androidx.compose.material.icons.rounded.Lightbulb
import androidx.compose.material.icons.rounded.Language
import androidx.compose.material.icons.rounded.Psychology
import androidx.compose.material.icons.rounded.Shield
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.foundation.horizontalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AttachFile
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.ChevronLeft
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.ChatBubble
import androidx.compose.material.icons.rounded.Extension
import androidx.compose.material.icons.rounded.Folder
import androidx.compose.material.icons.rounded.MoreVert
import androidx.compose.material.icons.rounded.Menu
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.automirrored.rounded.Send
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.Stop
import androidx.compose.material.icons.rounded.Work
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.InputChip
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationRail
import androidx.compose.material3.NavigationRailItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Slider
import androidx.compose.ui.zIndex
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.isShiftPressed
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.graphics.drawscope.clipRect
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import org.meo.ai.R
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.KeyboardType

// Generic renderer for the Meo AI core view (meo_ai_core::cloud::app, contract in
// meo/docs/cloud-core-view.md). It knows component kinds only, never product
// features: navigation, pages, settings and buttons all come from the core view,
// and every interaction sends back the action object attached to the element.

private fun JSONArray?.objects(): List<JSONObject> =
    if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it) }

private fun JSONObject.list(name: String): List<JSONObject> = optJSONArray(name).objects()
private fun JSONObject.str(name: String): String = if (isNull(name)) "" else optString(name, "")
private fun JSONObject.obj(name: String): JSONObject? = optJSONObject(name)

private fun JSONObject.withField(name: String, value: Any?): JSONObject =
    JSONObject(toString()).put(name, value)

private typealias Act = (JSONObject) -> Unit

private fun Act.send(action: JSONObject?) {
    if (action != null) this(action)
}

@Composable
fun CoreApp(view: JSONObject, act: (JSONObject) -> Unit) {
    val strings = view.obj("strings") ?: JSONObject()
    val sidebar = view.obj("sidebar")
    val page = view.obj("page") ?: JSONObject()
    val notice = view.obj("notice")

    view.obj("dialog")?.let { CoreDialog(it, act) }

    BoxWithConstraints(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        val wide = maxWidth >= 840.dp
        val drawer = rememberDrawerState(DrawerValue.Closed)
        val scope = rememberCoroutineScope()
        val content: @Composable () -> Unit = {
            Column(Modifier.fillMaxSize()) {
                if (notice != null) {
                    Banner(
                        text = notice.str("text"),
                        error = notice.str("kind") == "error",
                        actionLabel = notice.str("actionLabel").ifEmpty { strings.str("dismiss").ifEmpty { "Dismiss" } },
                        onAction = { act.send(notice.obj("action")) },
                    )
                }
                if (!view.optBoolean("online", true)) {
                    Banner(text = strings.str("offline").ifEmpty { "Offline — showing saved data" }, error = false)
                }
                Box(Modifier.weight(1f).fillMaxWidth()) {
                    val menu: (() -> Unit)? = if (wide || sidebar == null) null else ({ scope.launch { drawer.open() } })
                    when (page.str("kind")) {
                        "sign_in" -> SignInPage(page, act)
                        "conversation" -> ChatPane(page, view.obj("prefs"), strings, onMenu = menu, act = act, modifier = Modifier.fillMaxSize())
                        else -> Column(Modifier.fillMaxSize()) {
                            if (menu != null) IconButton(onClick = menu) { Icon(Icons.Rounded.Menu, contentDescription = "Menu") }
                            Box(Modifier.weight(1f)) {
                                when (page.str("kind")) {
                                    "list" -> ListPage(page, act)
                                    "store" -> StorePage(page, act)
                                    "settings" -> Box(Modifier.fillMaxSize())
                                    else -> UnavailablePage(page, act)
                                }
                            }
                        }
                    }
                }
            }
        }
        if (sidebar == null) {
            content()
        } else if (wide) {
            // The window is the sidebar's tone; the page is a raised, rounded card on top of it.
            Row(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surfaceContainer)) {
                ShellSidebar(sidebar, act, Modifier.width(if (sidebar.optBoolean("collapsed")) 60.dp else 260.dp).fillMaxHeight())
                Surface(
                    modifier = Modifier.weight(1f).fillMaxHeight().padding(top = 8.dp, end = 8.dp, bottom = 8.dp),
                    shape = RoundedCornerShape(20.dp),
                    color = MaterialTheme.colorScheme.background,
                    shadowElevation = 1.dp,
                    border = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.6f)),
                ) { content() }
            }
        } else {
            ModalNavigationDrawer(
                drawerState = drawer,
                drawerContent = {
                    ModalDrawerSheet {
                        // The drawer always shows the full sidebar, never the icon rail.
                        ShellSidebar(sidebar, { action -> scope.launch { drawer.close() }; act(action) }, Modifier.fillMaxHeight(), forceExpanded = true)
                    }
                },
            ) { content() }
        }
        if (page.str("kind") == "settings") SettingsDialog(page, act, wide)
    }
}

private fun navigationIcon(symbol: String): ImageVector = when (symbol) {
    "chat" -> Icons.Rounded.ChatBubble
    "work" -> Icons.Rounded.Work
    "folder" -> Icons.Rounded.Folder
    "extension" -> Icons.Rounded.Extension
    "settings" -> Icons.Rounded.Settings
    else -> Icons.Rounded.AutoAwesome
}

/** Generic modal question from the core: `prompt` has a text field, `confirm` does not. */
@Composable
private fun CoreDialog(dialog: JSONObject, act: Act) {
    val actions = dialog.list("actions")
    val confirm = actions.getOrNull(0)
    val cancel = actions.getOrNull(1)
    val input = dialog.obj("input")
    var value by remember(dialog.toString()) { mutableStateOf(input?.str("value") ?: "") }
    fun run(spec: JSONObject) {
        val action = spec.obj("action") ?: return
        act(if (spec.optBoolean("withInput")) action.withField("text", value) else action)
    }
    AlertDialog(
        onDismissRequest = { act(JSONObject().put("type", "close_dialog")) },
        title = { Text(dialog.str("title")) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                dialog.str("text").takeIf { it.isNotEmpty() }?.let { Text(it) }
                if (input != null) {
                    OutlinedTextField(
                        value = value,
                        onValueChange = { value = it },
                        singleLine = !input.optBoolean("multiline"),
                        minLines = if (input.optBoolean("multiline")) 4 else 1,
                        placeholder = { Text(input.str("placeholder")) },
                        visualTransformation = if (input.optBoolean("secret")) PasswordVisualTransformation() else VisualTransformation.None,
                        keyboardOptions = if (input.optBoolean("secret")) KeyboardOptions(keyboardType = KeyboardType.Password) else KeyboardOptions.Default,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        },
        confirmButton = {
            if (confirm != null) {
                TextButton(
                    onClick = { run(confirm) },
                    colors = if (confirm.str("style") == "danger")
                        ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error)
                    else ButtonDefaults.textButtonColors(),
                ) { Text(confirm.str("label")) }
            }
        },
        dismissButton = {
            if (cancel != null) TextButton(onClick = { run(cancel) }) { Text(cancel.str("label")) }
        },
    )
}

@Composable
private fun Banner(text: String, error: Boolean, actionLabel: String? = null, onAction: () -> Unit = {}) {
    Surface(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp),
        shape = RoundedCornerShape(16.dp),
        color = if (error) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.secondaryContainer,
    ) {
        Row(Modifier.padding(start = 16.dp, end = 8.dp, top = 8.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(text, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
            if (actionLabel != null) TextButton(onClick = onAction) { Text(actionLabel) }
        }
    }
}

@Composable
private fun ActionButton(spec: JSONObject, act: Act, modifier: Modifier = Modifier) {
    val onClick = { act.send(spec.obj("action")) }
    val label: @Composable () -> Unit = { Text(spec.str("label")) }
    when (spec.str("style")) {
        "primary" -> Button(onClick = onClick, modifier = modifier) { label() }
        "danger" -> OutlinedButton(
            onClick = onClick,
            modifier = modifier,
            colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.error),
        ) { label() }
        else -> FilledTonalButton(onClick = onClick, modifier = modifier) { label() }
    }
}

@Composable
private fun SignInPage(page: JSONObject, act: Act) {
    Column(
        Modifier.fillMaxSize().padding(horizontal = 32.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(20.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Image(painterResource(R.mipmap.ic_launcher), contentDescription = null, modifier = Modifier.size(72.dp))
        Text(page.str("title"), style = MaterialTheme.typography.headlineMedium)
        Text(
            page.str("text"),
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
        page.list("features").forEach { feature ->
            Row(Modifier.fillMaxWidth().widthIn(max = 420.dp), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Surface(shape = RoundedCornerShape(12.dp), color = MaterialTheme.colorScheme.secondaryContainer, modifier = Modifier.size(40.dp)) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            navigationIcon(feature.str("icon").let { if (it == "skills") "extension" else it }),
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.onSecondaryContainer,
                        )
                    }
                }
                Column {
                    Text(feature.str("title"), style = MaterialTheme.typography.titleSmall)
                    Text(feature.str("text"), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
        if (page.optBoolean("busy")) CircularProgressIndicator()
        page.list("actions").forEach { ActionButton(it, act) }
    }
}

/** Chat | Work as one pill: the thumb slides between the labels (not two separate buttons). */
@Composable
private fun ModeSwitch(modes: List<JSONObject>, act: Act, modifier: Modifier = Modifier) {
    val selected = modes.indexOfFirst { it.optBoolean("selected") }.coerceAtLeast(0)
    val count = modes.size.coerceAtLeast(1)
    BoxWithConstraints(
        modifier.height(36.dp).clip(RoundedCornerShape(50)).background(MaterialTheme.colorScheme.surfaceContainerHigh).padding(3.dp),
    ) {
        val cell = maxWidth / count
        val thumbX by androidx.compose.animation.core.animateDpAsState(
            cell * selected,
            androidx.compose.animation.core.tween(200, easing = androidx.compose.animation.core.FastOutSlowInEasing),
            label = "modeThumb",
        )
        Surface(
            Modifier.offset(x = thumbX).width(cell).fillMaxHeight(),
            shape = RoundedCornerShape(50),
            color = MaterialTheme.colorScheme.surface,
            shadowElevation = 1.dp,
        ) {}
        Row(Modifier.fillMaxSize()) {
            modes.forEachIndexed { index, mode ->
                Box(
                    Modifier.weight(1f).fillMaxHeight().clip(RoundedCornerShape(50))
                        .clickable(role = androidx.compose.ui.semantics.Role.Tab) { act.send(mode.obj("action")) },
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        mode.str("label"),
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = if (index == selected) FontWeight.SemiBold else FontWeight.Normal,
                        color = if (index == selected) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

/** Settings float over the app: one dialog card with the close button in its top-right corner
 *  (a full screen on a phone). Back and a tap outside close it too. */
@Composable
private fun SettingsDialog(page: JSONObject, act: Act, wide: Boolean) {
    androidx.compose.ui.window.Dialog(
        onDismissRequest = { act.send(page.obj("close")) },
        properties = androidx.compose.ui.window.DialogProperties(usePlatformDefaultWidth = false),
    ) {
        Surface(
            modifier = if (wide) Modifier.fillMaxWidth(0.92f).widthIn(max = 940.dp).fillMaxHeight(0.9f).heightIn(max = 660.dp) else Modifier.fillMaxSize(),
            shape = RoundedCornerShape(if (wide) 24.dp else 0.dp),
            color = MaterialTheme.colorScheme.surface,
            shadowElevation = 6.dp,
        ) {
            Column(Modifier.fillMaxSize()) {
                Row(Modifier.fillMaxWidth().padding(start = 20.dp, end = 8.dp, top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(page.str("title"), Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
                    IconButton(onClick = { act.send(page.obj("close")) }) { Icon(Icons.Rounded.Close, contentDescription = "Close") }
                }
                androidx.compose.material3.HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                Box(Modifier.weight(1f)) { SettingsPage(page, act) }
            }
        }
    }
}

/** Three dots that bounce in a wave while the answer has not started. */
@Composable
private fun TypingDots() {
    val transition = androidx.compose.animation.core.rememberInfiniteTransition(label = "typing")
    Row(Modifier.padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(5.dp)) {
        repeat(3) { i ->
            val lift by transition.animateFloat(
                initialValue = 0f,
                targetValue = 0f,
                animationSpec = androidx.compose.animation.core.infiniteRepeatable(
                    animation = androidx.compose.animation.core.keyframes {
                        durationMillis = 1100
                        0f at 0
                        1f at 330
                        0f at 700
                    },
                    initialStartOffset = androidx.compose.animation.core.StartOffset(i * 140),
                ),
                label = "dot$i",
            )
            Box(
                Modifier.size(7.dp)
                    .graphicsLayer { translationY = -4.dp.toPx() * lift }
                    .clip(RoundedCornerShape(50))
                    .background(MaterialTheme.colorScheme.primary.copy(alpha = 0.4f + 0.6f * lift)),
            )
        }
    }
}

private class StepKind(val icon: androidx.compose.ui.graphics.vector.ImageVector, val live: String)

/** What a step is doing, from its id and title (the core sends free text). */
private fun stepKind(step: JSONObject?): StepKind {
    if (step == null) return StepKind(Icons.Rounded.Psychology, "Thinking")
    val title = step.str("title")
    val l = (step.str("id") + " " + title).lowercase()
    fun has(pattern: String) = Regex(pattern).containsMatchIn(l)
    return when {
        has("connect|mcp|connector|oauth|authori[sz]") -> StepKind(Icons.Rounded.Cable, if (title.isNotEmpty()) "Connecting · $title" else "Connecting")
        has("search|web|browse|fetch|http") -> StepKind(Icons.Rounded.Language, "Searching the web")
        has("image|picture|draw") -> StepKind(Icons.Rounded.Image, "Creating an image")
        has("edit|write|patch|save|create file|apply|modif") -> StepKind(Icons.Rounded.EditNote, "Editing files")
        has("read|open|list|find|grep|glob|scan|index") -> StepKind(Icons.Rounded.Description, "Reading files")
        has("run|command|shell|bash|exec|terminal|test|build|install") -> StepKind(Icons.Rounded.Terminal, "Running a command")
        has("model|router|reason|think|plan") -> StepKind(Icons.Rounded.Psychology, "Thinking")
        has("tool\\d+") -> StepKind(Icons.Rounded.Build, "Using tools")
        else -> StepKind(Icons.Rounded.Bolt, title.ifEmpty { "Working" })
    }
}

/** The step a streaming answer is on now: the last one still running, else the last one. */
private fun currentStep(steps: List<JSONObject>): JSONObject? =
    steps.lastOrNull { it.str("status") != "done" && it.str("status") != "error" } ?: steps.lastOrNull()

/** What the assistant is doing right now: a breathing icon, the sentence with a light sweeping
 *  over it, and the elapsed time once it is worth showing. */
@Composable
private fun LiveStatus(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String) {
    var seconds by remember { mutableStateOf(0) }
    LaunchedEffect(Unit) { while (true) { kotlinx.coroutines.delay(1000); seconds += 1 } }
    val transition = androidx.compose.animation.core.rememberInfiniteTransition(label = "live")
    val halo by transition.animateFloat(
        initialValue = 0.9f,
        targetValue = 1.25f,
        animationSpec = androidx.compose.animation.core.infiniteRepeatable(
            androidx.compose.animation.core.tween(700, easing = androidx.compose.animation.core.FastOutSlowInEasing),
            androidx.compose.animation.core.RepeatMode.Reverse,
        ),
        label = "halo",
    )
    val sweep by transition.animateFloat(
        initialValue = -300f,
        targetValue = 600f,
        animationSpec = androidx.compose.animation.core.infiniteRepeatable(
            androidx.compose.animation.core.tween(1600, easing = androidx.compose.animation.core.LinearEasing),
        ),
        label = "sweep",
    )
    val base = MaterialTheme.colorScheme.onSurfaceVariant
    val light = MaterialTheme.colorScheme.onSurface
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Box(Modifier.size(22.dp), contentAlignment = Alignment.Center) {
            Box(
                Modifier.size(22.dp)
                    .graphicsLayer { scaleX = halo; scaleY = halo }
                    .clip(RoundedCornerShape(50))
                    .background(MaterialTheme.colorScheme.primary.copy(alpha = 0.14f)),
            )
            Icon(icon, contentDescription = null, Modifier.size(14.dp), tint = MaterialTheme.colorScheme.primary)
        }
        Text(
            label + "…",
            style = MaterialTheme.typography.labelMedium.copy(
                fontWeight = androidx.compose.ui.text.font.FontWeight.Medium,
                brush = androidx.compose.ui.graphics.Brush.linearGradient(
                    colors = listOf(base, light, base),
                    start = androidx.compose.ui.geometry.Offset(sweep, 0f),
                    end = androidx.compose.ui.geometry.Offset(sweep + 300f, 0f),
                ),
            ),
        )
        if (seconds >= 5) {
            Text(
                if (seconds >= 60) "${seconds / 60}m ${seconds % 60}s" else "${seconds}s",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.outline,
            )
        }
    }
}

@Composable
private fun UnavailablePage(page: JSONObject, act: Act) {
    Column(
        Modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(page.str("title"), style = MaterialTheme.typography.headlineSmall)
        Text(
            page.str("text"),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
        page.list("actions").forEach { ActionButton(it, act) }
    }
}

@Composable
private fun ListPage(page: JSONObject, act: Act) {
    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().padding(start = 20.dp, end = 12.dp, top = 16.dp, bottom = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(page.str("title"), Modifier.weight(1f), style = MaterialTheme.typography.headlineMedium)
            page.list("actions").forEach { ActionButton(it, act) }
        }
        if (page.optBoolean("loading")) {
            CircularProgressIndicator(Modifier.align(Alignment.CenterHorizontally).padding(16.dp))
        }
        page.obj("empty")?.let {
            Text(
                it.str("title"),
                Modifier.fillMaxWidth().padding(32.dp),
                textAlign = TextAlign.Center,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        LazyColumn(Modifier.weight(1f).fillMaxWidth()) {
            items(page.list("items")) { item ->
                val action = item.obj("action")
                val subtitle = item.str("subtitle")
                ListItem(
                    headlineContent = { Text(item.str("title")) },
                    supportingContent = if (subtitle.isNotEmpty()) { { Text(subtitle, maxLines = 2) } } else null,
                    modifier = if (action != null) Modifier.clickable { act(action) } else Modifier,
                )
            }
        }
    }
}

@Composable
private fun SettingsPage(page: JSONObject, act: Act) {
    val sections = page.list("sections")
    val current = sections.firstOrNull { it.str("id") == page.str("selected") } ?: sections.firstOrNull()
    val entries = page.list("nav").flatMap { it.list("items") }
    Column(Modifier.fillMaxSize().padding(8.dp)) {
        page.obj("search")?.let { search ->
            var text by remember(search.str("value")) { mutableStateOf(search.str("value")) }
            LaunchedEffect(text) {
                if (text != search.str("value")) {
                    kotlinx.coroutines.delay(250)
                    act.send(search.obj("action")?.withField(search.str("field"), text))
                }
            }
            OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                singleLine = true,
                placeholder = { Text(search.str("placeholder")) },
                modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp),
            )
        }
        // Categories: one scrolling row of chips (a card with a side list does not fit a phone).
        androidx.compose.foundation.lazy.LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), contentPadding = PaddingValues(horizontal = 8.dp)) {
            items(entries) { e ->
                FilterChip(selected = e.optBoolean("selected"), onClick = { act.send(e.obj("action")) }, label = { Text(e.str("label")) })
            }
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(current?.str("label") ?: page.str("title"), style = MaterialTheme.typography.headlineSmall)
            // A heading starts a group: its rows sit in one rounded card, hints are notes under it.
            val groups = mutableListOf<Triple<String, MutableList<JSONObject>, MutableList<JSONObject>>>()
            var g = Triple("", mutableListOf<JSONObject>(), mutableListOf<JSONObject>())
            current?.list("items")?.forEach { it0 ->
                when (it0.str("kind")) {
                    "heading" -> { if (g.second.isNotEmpty() || g.third.isNotEmpty() || g.first.isNotEmpty()) groups.add(g); g = Triple(it0.str("label"), mutableListOf(), mutableListOf()) }
                    "hint" -> g.third.add(it0)
                    else -> g.second.add(it0)
                }
            }
            if (g.second.isNotEmpty() || g.third.isNotEmpty()) groups.add(g)
            groups.forEach { (title, rows, notes) ->
                if (title.isNotEmpty()) Text(title, Modifier.padding(start = 4.dp, top = 8.dp), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                if (rows.isNotEmpty()) Surface(shape = RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.surfaceContainerLow, border = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)) {
                    Column {
                        rows.forEachIndexed { i, row ->
                            if (i > 0) androidx.compose.material3.HorizontalDivider(Modifier.padding(start = 16.dp), color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.6f))
                            SettingControl(row, act, Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp))
                        }
                    }
                }
                notes.forEach { Text(it.str("text"), Modifier.padding(horizontal = 4.dp), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            }
        }
    }
}

private fun setting(item: JSONObject, value: Any?): JSONObject =
    JSONObject().put("type", "set_setting").put("binding", item.str("binding")).put("value", value)

/** Name and a quiet description (a status dot first when the core gives a tone). */
@Composable
private fun RowText(item: JSONObject, modifier: Modifier = Modifier) {
    val note = if (item.optBoolean("keys")) "" else item.str("description").ifEmpty { if (item.str("kind") == "item") item.str("value") else "" }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(item.str("label"), style = MaterialTheme.typography.bodyLarge)
        if (note.isNotEmpty()) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            val tone = item.str("tone")
            if (tone.isNotEmpty()) Box(
                Modifier.size(8.dp).clip(RoundedCornerShape(50)).background(
                    when (tone) {
                        "ok" -> androidx.compose.ui.graphics.Color(0xFF2E7D32)
                        "error" -> MaterialTheme.colorScheme.error
                        else -> androidx.compose.ui.graphics.Color(0xFFB26A00)
                    },
                ),
            )
            Text(note, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

/** A key combination as key caps. */
@Composable
private fun KeyCaps(combo: String) {
    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        combo.split("+").filter { it.isNotEmpty() }.forEach { key ->
            Surface(shape = RoundedCornerShape(7.dp), color = MaterialTheme.colorScheme.surfaceContainerHighest, border = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)) {
                Text(key, Modifier.padding(horizontal = 8.dp, vertical = 3.dp), style = MaterialTheme.typography.labelMedium)
            }
        }
    }
}

@Composable
private fun SettingControl(item: JSONObject, act: Act, modifier: Modifier = Modifier.fillMaxWidth()) {
    when (item.str("kind")) {
        "toggle" -> Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            RowText(item, Modifier.weight(1f))
            Switch(checked = item.optBoolean("value"), onCheckedChange = { act(setting(item, it)) })
        }
        "slider" -> {
            val options = item.list("options")
            val index = options.indexOfFirst { it.str("value") == item.str("value") }.coerceAtLeast(0)
            Column(modifier) {
                RowText(item)
                Text(options.getOrNull(index)?.str("label") ?: "", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
                Slider(
                    value = index.toFloat(),
                    onValueChange = { v -> options.getOrNull(v.toInt())?.let { if (it.str("value") != item.str("value")) act(setting(item, it.str("value"))) } },
                    valueRange = 0f..(options.size - 1).coerceAtLeast(1).toFloat(),
                    steps = (options.size - 2).coerceAtLeast(0),
                )
            }
        }
        "hint" -> Text(item.str("text"), modifier, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        "heading" -> Text(item.str("label"), modifier.padding(top = 6.dp), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        "stats" -> Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            item.list("items").chunked(3).forEach { rowTiles ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    rowTiles.forEach { t ->
                        Surface(Modifier.weight(1f), shape = RoundedCornerShape(14.dp), color = MaterialTheme.colorScheme.surfaceContainer) {
                            Column(Modifier.padding(horizontal = 12.dp, vertical = 8.dp)) {
                                Text(t.str("label"), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text(t.str("value"), style = MaterialTheme.typography.titleMedium, maxLines = 1)
                                if (t.str("hint").isNotEmpty()) Text(t.str("hint"), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2, overflow = TextOverflow.Ellipsis)
                            }
                        }
                    }
                    repeat(3 - rowTiles.size) { Spacer(Modifier.weight(1f)) }
                }
            }
        }
        "bars" -> Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(item.str("label"), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            val bars = item.list("items")
            val peak = bars.maxOfOrNull { it.optDouble("value") }?.coerceAtLeast(1.0) ?: 1.0
            Row(Modifier.fillMaxWidth().height(72.dp), horizontalArrangement = Arrangement.spacedBy(3.dp), verticalAlignment = Alignment.Bottom) {
                bars.forEach { b ->
                    Box(
                        Modifier.weight(1f).fillMaxHeight((b.optDouble("value") / peak).toFloat().coerceIn(0.04f, 1f))
                            .clip(RoundedCornerShape(topStart = 3.dp, topEnd = 3.dp))
                            .background(MaterialTheme.colorScheme.primary.copy(alpha = 0.75f)),
                    )
                }
            }
        }
        "select" -> SelectControl(item, act, modifier)
        "text" -> TextControl(item, act, modifier)
        "info" -> Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            RowText(item, Modifier.weight(1f))
            if (item.optBoolean("keys")) KeyCaps(item.str("value"))
            else Text(item.str("value"), color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        "button" -> ActionButton(item, act, modifier)
        "item" -> {
            val buttons = item.list("buttons")
            val below = buttons.size > 2
            Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    RowText(item, Modifier.weight(1f))
                    if (item.optBoolean("keys")) KeyCaps(item.str("value"))
                    item.obj("switch")?.let { sw -> Switch(checked = sw.optBoolean("on"), onCheckedChange = { act.send(sw.obj("action")) }) }
                    if (!below) buttons.forEach { ActionButton(it, act) }
                }
                if (below) FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) { buttons.forEach { ActionButton(it, act) } }
            }
        }
    }
}

@Composable
private fun SelectControl(item: JSONObject, act: Act, modifier: Modifier) {
    var open by remember { mutableStateOf(false) }
    val options = item.list("options")
    val current = options.firstOrNull { it.str("value") == item.str("value") }
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        RowText(item, Modifier.weight(1f))
        Box {
            OutlinedButton(onClick = { open = true }, enabled = options.isNotEmpty(), shape = RoundedCornerShape(50)) {
                Text(current?.str("label") ?: "—", maxLines = 1, overflow = TextOverflow.Ellipsis)
                Icon(Icons.Rounded.ExpandMore, contentDescription = null, modifier = Modifier.size(18.dp))
            }
            DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                options.forEach { option ->
                    DropdownMenuItem(
                        text = { Text(option.str("label")) },
                        onClick = {
                            open = false
                            act(setting(item, option.str("value")))
                        },
                    )
                }
            }
        }
    }
}

@Composable
private fun TextControl(item: JSONObject, act: Act, modifier: Modifier) {
    val saved = item.str("value")
    var text by remember(saved) { mutableStateOf(saved) }
    val singleLine = item.optBoolean("single_line")
    val hint = item.str("placeholder")
    val commit = { if (text != saved) act(setting(item, text)) }
    // Phones have no reliable "blur": also save when typing pauses.
    LaunchedEffect(text) {
        if (text != saved) {
            kotlinx.coroutines.delay(800)
            act(setting(item, text))
        }
    }
    OutlinedTextField(
        value = text,
        onValueChange = { text = it },
        modifier = modifier.onFocusChanged { if (!it.isFocused) commit() },
        label = { Text(item.str("label")) },
        placeholder = if (hint.isNotEmpty()) { { Text(hint) } } else null,
        singleLine = singleLine,
        minLines = if (singleLine) 1 else 3,
        keyboardOptions = KeyboardOptions(imeAction = if (singleLine) ImeAction.Done else ImeAction.Default),
        keyboardActions = KeyboardActions(onDone = { commit() }),
    )
}

/** Claude-style left column: Chat | Work, search, new chat, plugins, projects tree, chats. */
@Composable
private fun ShellSidebar(sb: JSONObject, act: Act, modifier: Modifier, forceExpanded: Boolean = false) {
    val collapsed = sb.optBoolean("collapsed") && !forceExpanded
    val rows = remember(sb.toString(), collapsed) {
        val out = mutableListOf<Triple<String, JSONObject, Int>>()
        sb.list("sections").forEach { sec ->
            if (sec.str("kind") == "list") {
                if (!collapsed) {
                    out.add(Triple("header", sec, 0))
                    sec.list("items").forEach { out.add(Triple("item", it, 0)) }
                }
            } else {
                out.add(Triple("link", sec, 0))
                if (sec.str("kind") == "tree" && !collapsed) {
                    sec.list("items").forEach { p ->
                        out.add(Triple("item", p, 1))
                        p.list("children").forEach { out.add(Triple("item", it, 2)) }
                    }
                }
            }
        }
        out
    }
    Column(modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            // The toggle sits at the top-left corner in both states; the Chat | Work switch follows it.
            if (!forceExpanded) {
                IconButton(onClick = { act.send(sb.obj("toggle")) }) {
                    Icon(Icons.Rounded.ViewSidebar, contentDescription = if (collapsed) "Show sidebar" else "Hide sidebar")
                }
            }
            if (!collapsed) {
                ModeSwitch(sb.list("modes"), act, Modifier.weight(1f))
            }
        }
        if (collapsed) {
            sb.list("modes").forEach { mode ->
                IconButton(onClick = { act.send(mode.obj("action")) }) {
                    Icon(navigationIcon(if (mode.str("icon") == "work") "work" else "chat"), contentDescription = mode.str("label"))
                }
            }
        } else {
            sb.obj("search")?.let { SearchField(it, act) }
        }
        sb.obj("newChat")?.let { n ->
            TextButton(onClick = { act.send(n.obj("action")) }, modifier = Modifier.fillMaxWidth()) {
                Icon(Icons.Rounded.Add, contentDescription = n.str("label"))
                if (!collapsed) Text(n.str("label"), Modifier.weight(1f).padding(start = 12.dp))
            }
        }
        LazyColumn(Modifier.weight(1f)) {
            items(rows) { (kind, item, depth) ->
                when (kind) {
                    "link" -> {
                        val on = item.optBoolean("selected")
                        TextButton(
                            onClick = { act.send(item.obj("action")) },
                            modifier = Modifier.fillMaxWidth(),
                            colors = if (on) ButtonDefaults.textButtonColors(containerColor = MaterialTheme.colorScheme.secondaryContainer) else ButtonDefaults.textButtonColors(),
                        ) {
                            Icon(navigationIcon(item.str("icon").let { if (it == "skills") "extension" else if (it == "projects") "folder" else it }), contentDescription = item.str("label"))
                            if (!collapsed) Text(item.str("label"), Modifier.weight(1f).padding(start = 12.dp))
                        }
                    }
                    "header" -> Column(Modifier.padding(top = 8.dp)) {
                        Text(item.str("label"), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            item.list("tabs").forEach { tab ->
                                FilterChip(selected = tab.optBoolean("selected"), onClick = { act.send(tab.obj("action")) }, label = { Text(tab.str("label")) })
                            }
                        }
                    }
                    else -> SideRow(item, depth, act)
                }
            }
        }
        sb.list("footer").forEach { f ->
            TextButton(onClick = { act.send(f.obj("action")) }, modifier = Modifier.fillMaxWidth()) {
                Icon(navigationIcon("settings"), contentDescription = f.str("label"))
                if (!collapsed) Text(f.str("label"), Modifier.weight(1f).padding(start = 12.dp))
            }
        }
    }
}

@Composable
private fun SideRow(item: JSONObject, depth: Int, act: Act) {
    val selected = item.optBoolean("selected")
    var menuOpen by remember { mutableStateOf(false) }
    Surface(
        onClick = { act.send(item.obj("action")) },
        shape = RoundedCornerShape(16.dp),
        color = if (selected) MaterialTheme.colorScheme.secondaryContainer else androidx.compose.ui.graphics.Color.Transparent,
        modifier = Modifier.fillMaxWidth().padding(start = (depth * 12).dp),
    ) {
        Row(Modifier.padding(start = 16.dp, top = 4.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f).padding(vertical = 6.dp)) {
                Text(item.str("title"), maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            val menu = item.list("menu")
            if (menu.isNotEmpty()) {
                Box {
                    IconButton(onClick = { menuOpen = true }) { Icon(Icons.Rounded.MoreVert, contentDescription = "⋮") }
                    DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                        menu.forEach { entry ->
                            DropdownMenuItem(
                                text = {
                                    Text(
                                        entry.str("label"),
                                        color = if (entry.str("style") == "danger") MaterialTheme.colorScheme.error
                                        else androidx.compose.ui.graphics.Color.Unspecified,
                                    )
                                },
                                onClick = { menuOpen = false; act.send(entry.obj("action")) },
                            )
                        }
                    }
                }
            }
        }
    }
}

/** Search field: the text is sent as `text` on the search action, debounced. */
@Composable
private fun SearchField(search: JSONObject, act: Act) {
    val saved = search.str("value")
    var text by remember(saved) { mutableStateOf(saved) }
    LaunchedEffect(text) {
        if (text != saved) {
            kotlinx.coroutines.delay(300)
            search.obj("action")?.let { act(it.withField("text", text)) }
        }
    }
    Row(
        Modifier.fillMaxWidth().heightIn(min = 40.dp).background(MaterialTheme.colorScheme.surfaceContainerHigh, androidx.compose.foundation.shape.CircleShape).padding(horizontal = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(Icons.Rounded.Search, contentDescription = null, modifier = Modifier.size(18.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
        BasicTextField(
            value = text,
            onValueChange = { text = it },
            modifier = Modifier.weight(1f),
            singleLine = true,
            textStyle = MaterialTheme.typography.bodyMedium.copy(color = MaterialTheme.colorScheme.onSurface),
            cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
            decorationBox = { inner ->
                if (text.isEmpty()) Text(search.str("placeholder"), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                inner()
            },
        )
    }
}

@Composable
private fun ChatPane(page: JSONObject, prefs: JSONObject?, strings: JSONObject, onMenu: (() -> Unit)?, act: Act, modifier: Modifier) {
    val messages = page.list("messages")
    val composer = page.obj("composer") ?: JSONObject()
    val consent = page.obj("consent")
    val listState = rememberLazyListState()
    val lastLength = messages.lastOrNull()?.str("text")?.length ?: 0

    LaunchedEffect(messages.size, lastLength) {
        if (messages.isNotEmpty()) listState.scrollToItem(messages.size - 1)
    }

    Column(modifier.imePadding()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            if (onMenu != null) IconButton(onClick = onMenu) { Icon(Icons.Rounded.Menu, contentDescription = "Chats") }
            Text(
                page.str("title"),
                Modifier.padding(horizontal = 8.dp).weight(1f),
                style = MaterialTheme.typography.titleMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            val chatMenu = page.list("menu")
            if (chatMenu.isNotEmpty()) {
                var open by remember { mutableStateOf(false) }
                Box {
                    IconButton(onClick = { open = true }) { Icon(Icons.Rounded.MoreVert, contentDescription = "⋮") }
                    DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                        chatMenu.forEach { entry ->
                            DropdownMenuItem(
                                text = { Text(entry.str("label"), color = if (entry.str("style") == "danger") MaterialTheme.colorScheme.error else androidx.compose.ui.graphics.Color.Unspecified) },
                                onClick = { open = false; act.send(entry.obj("action")) },
                            )
                        }
                    }
                }
            }
        }
        BoxWithConstraints(Modifier.weight(1f).fillMaxWidth()) {
            val empty = page.obj("empty")
            val fresh = empty != null
            val density = androidx.compose.ui.platform.LocalDensity.current
            var composerPx by remember { androidx.compose.runtime.mutableIntStateOf(0) }
            val areaPx = with(density) { maxHeight.toPx() }
            val margin = with(density) { 8.dp.toPx() }
            // A new chat keeps the composer in the middle; it glides down (fast ease-out) once there is a conversation.
            val lift by androidx.compose.animation.core.animateFloatAsState(
                if (fresh) 1f else 0f,
                androidx.compose.animation.core.tween(240, easing = androidx.compose.animation.core.FastOutSlowInEasing),
                label = "composerLift",
            )
            val composerDp = with(density) { composerPx.toDp() }
            if (empty != null) {
                Column(
                    Modifier.align(Alignment.Center).offset(y = -(composerDp / 2 + 64.dp)).padding(horizontal = 32.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Image(painterResource(R.mipmap.ic_launcher), contentDescription = null, modifier = Modifier.size(48.dp))
                    Text(empty.str("title"), style = MaterialTheme.typography.headlineSmall, textAlign = TextAlign.Center)
                    Text(
                        empty.str("text"),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        textAlign = TextAlign.Center,
                    )
                }
            }
            val inspector = page.obj("inspector")
            if (inspector != null) {
                Box(Modifier.align(Alignment.TopEnd).padding(8.dp).zIndex(1f)) {
                    if (inspector.optBoolean("visible")) {
                        Card(Modifier.width(268.dp)) {
                            Column(Modifier.padding(horizontal = 14.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(inspector.str("title"), Modifier.weight(1f), style = MaterialTheme.typography.titleSmall)
                                    IconButton(onClick = { act.send(inspector.obj("hide")) }, Modifier.size(28.dp)) { Icon(Icons.Rounded.Close, contentDescription = "Hide") }
                                }
                                androidx.compose.material3.HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                                inspector.list("sections").forEachIndexed { i, sec ->
                                    if (i > 0) androidx.compose.material3.HorizontalDivider(Modifier.padding(vertical = 6.dp), color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.6f))
                                    InspectorSection(sec)
                                }
                            }
                        }
                    } else {
                        androidx.compose.material3.AssistChip(onClick = { act.send(inspector.obj("show")) }, label = { Text(inspector.str("title")) })
                    }
                }
            }
            LazyColumn(
                Modifier.fillMaxSize(),
                state = listState,
                contentPadding = PaddingValues(
                    start = 16.dp,
                    top = 8.dp,
                    // On a wide screen the Details card sits beside the chat, not over it.
                    end = if (inspector?.optBoolean("visible") == true && androidx.compose.ui.platform.LocalConfiguration.current.screenWidthDp >= 840) 292.dp else 16.dp,
                    bottom = if (fresh) 8.dp else composerDp + 8.dp,
                ),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(messages) { MessageBubble(it, strings, act) }
            }
            val scope = rememberCoroutineScope()
            val showJump by remember { androidx.compose.runtime.derivedStateOf { messages.isNotEmpty() && listState.canScrollForward } }
            if (showJump) {
                androidx.compose.material3.SmallFloatingActionButton(
                    onClick = { scope.launch { listState.animateScrollToItem(messages.size - 1) } },
                    modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = composerDp + 12.dp),
                    containerColor = MaterialTheme.colorScheme.surfaceContainerHigh,
                    contentColor = MaterialTheme.colorScheme.onSurface,
                ) { Icon(Icons.Rounded.ArrowDownward, contentDescription = strings.str("jump").ifEmpty { "Jump to the latest message" }) }
            }
            Column(
                Modifier.align(Alignment.BottomCenter)
                    .widthIn(max = 720.dp)
                    .onSizeChanged { composerPx = it.height }
                    .offset { IntOffset(0, -(lift * maxOf(0f, areaPx / 2f - composerPx / 2f - margin)).toInt()) },
            ) {
                if (consent != null) {
                    Card(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp)) {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(consent.str("title"), style = MaterialTheme.typography.titleMedium)
                            Text(consent.str("text"), color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                consent.list("actions").forEach { ActionButton(it, act) }
                            }
                        }
                    }
                }
                Composer(composer, page.list("files"), prefs, strings, act)
                if (fresh) {
                    FlowRow(Modifier.padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        empty?.list("suggestions")?.forEach { s ->
                            androidx.compose.material3.AssistChip(onClick = { act.send(s.obj("action")) }, label = { Text(s.str("label"), style = MaterialTheme.typography.labelMedium) })
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun MessageBubble(message: JSONObject, strings: JSONObject, act: Act) {
    val mine = message.str("role") == "user"
    val streaming = message.optBoolean("streaming")
    val text = message.str("text") + if (streaming && message.str("text").isNotEmpty()) " ▍" else ""
    val clipboard = LocalClipboardManager.current
    Column(Modifier.fillMaxWidth(), horizontalAlignment = if (mine) Alignment.End else Alignment.Start) {
        if (mine) {
            Surface(
                shape = RoundedCornerShape(18.dp),
                color = MaterialTheme.colorScheme.secondaryContainer,
                modifier = Modifier.widthIn(max = 320.dp),
            ) {
                SelectionContainer {
                    Text(text, Modifier.padding(horizontal = 16.dp, vertical = 10.dp))
                }
            }
        } else {
            SelectionContainer {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (message.has("steps")) Steps(message, act)
                    val blocks = message.list("blocks")
                    if (streaming && !message.has("steps") && message.str("text").isEmpty() && blocks.isEmpty()) LiveStatus(Icons.Rounded.Psychology, "Thinking")
                    if (streaming && message.str("text").isEmpty() && blocks.isEmpty()) TypingDots()
                    if (blocks.isEmpty()) MarkdownText(stripIcons(text), Modifier.fillMaxWidth())
                    else blocks.forEachIndexed { i, block ->
                        val cursor = if (streaming && i == blocks.lastIndex) " ▍" else ""
                        when (block.str("type")) {
                            "callout" -> CalloutBlock(block)
                            "draft" -> DraftBlock(block, strings)
                            "math" -> MathBlock(block)
                            "plot" -> PlotBlock(block)
                            "chart" -> ChartBlock(block)
                            else -> MarkdownText(stripIcons(block.str("text")) + cursor, Modifier.fillMaxWidth())
                        }
                    }
                    message.list("images").forEach { image ->
                        AsyncImage(
                            model = image.str("url"),
                            contentDescription = null,
                            contentScale = ContentScale.Fit,
                            modifier = Modifier.fillMaxWidth().heightIn(max = 420.dp).clip(RoundedCornerShape(14.dp)),
                        )
                    }
                }
            }
        }
        if (!streaming && message.str("text").isNotEmpty()) {
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                TextButton(onClick = { clipboard.setText(AnnotatedString(message.str("text"))) }) { Text(strings.str("copy").ifEmpty { "Copy" }) }
                message.list("actions").forEach { entry ->
                    TextButton(onClick = { act.send(entry.obj("action")) }) { Text(entry.str("label")) }
                }
            }
        }
    }
}

/** Quiet text control under the composer; slider and select open a small menu. */
@Composable
private fun ControlChip(item: JSONObject, act: Act) {
    var open by remember { mutableStateOf(false) }
    val options = item.list("options")
    val index = options.indexOfFirst { it.str("value") == item.str("value") }.coerceAtLeast(0)
    val kind = item.str("kind")
    val symbol = when (item.str("icon")) {
        "language" -> Icons.Rounded.Language
        "account_tree" -> Icons.Rounded.AccountTree
        "shield" -> Icons.Rounded.Shield
        "psychology" -> Icons.Rounded.Psychology
        else -> null
    }
    // Toggles with an icon are icon-only; the name is the accessibility label.
    if (kind == "toggle" && symbol != null) {
        androidx.compose.material3.IconToggleButton(checked = item.optBoolean("value"), onCheckedChange = { act(setting(item, it)) }) {
            Icon(symbol, contentDescription = item.str("label"))
        }
        return
    }
    Box {
        TextButton(
            onClick = { if (kind == "toggle") act(setting(item, !item.optBoolean("value"))) else open = true },
            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp),
        ) {
            if (symbol != null) Icon(symbol, contentDescription = null, modifier = Modifier.size(16.dp).padding(end = 0.dp))
            Text(
                (if (symbol != null) " " else "") + if (kind == "toggle") (if (item.optBoolean("value")) "● " else "○ ") + item.str("label")
                else (options.getOrNull(index)?.str("label") ?: item.str("label")) + " ▾",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            if (kind == "slider") {
                Column(Modifier.padding(horizontal = 16.dp).widthIn(min = 200.dp)) {
                    Text(item.str("label") + " · " + (options.getOrNull(index)?.str("label") ?: ""), style = MaterialTheme.typography.labelMedium)
                    Slider(
                        value = index.toFloat(),
                        onValueChange = { v -> options.getOrNull(v.toInt())?.let { if (it.str("value") != item.str("value")) act(setting(item, it.str("value"))) } },
                        valueRange = 0f..(options.size - 1).coerceAtLeast(1).toFloat(),
                        steps = (options.size - 2).coerceAtLeast(0),
                    )
                }
            } else {
                options.forEach { o ->
                    DropdownMenuItem(text = { Text(o.str("label")) }, onClick = { open = false; act(setting(item, o.str("value"))) })
                }
            }
        }
    }
}

/** Collapsible list of what the core did for this answer (model, web search, ...). While it runs
 *  the header says what it is doing now; each step has an icon and the running one pulses. */
@Composable
private fun Steps(message: JSONObject, act: Act) {
    val auto = message.optBoolean("stepsOpen")
    var toggled by remember { mutableStateOf<Boolean?>(null) }
    val open = toggled ?: auto
    val context = LocalContext.current
    val steps = message.list("steps")
    val running = message.optBoolean("streaming")
    val muted = MaterialTheme.colorScheme.onSurfaceVariant
    Column(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
        Row(
            Modifier.clickable { toggled = !open }.padding(vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            if (running) {
                val kind = stepKind(currentStep(steps))
                LiveStatus(kind.icon, kind.live)
            } else {
                Icon(Icons.Rounded.CheckCircle, contentDescription = null, Modifier.size(16.dp), tint = muted)
                Text(message.str("stepsLabel"), style = MaterialTheme.typography.labelMedium, color = muted)
            }
            Icon(if (open) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore, contentDescription = null, Modifier.size(16.dp), tint = muted)
        }
        if (open) {
            steps.forEach { step ->
                var expanded by remember { mutableStateOf(false) }
                val more = step.str("detail").isNotEmpty() || step.list("items").isNotEmpty()
                val status = step.str("status")
                val live = status != "done" && status != "error"
                val pulse by androidx.compose.animation.core.rememberInfiniteTransition(label = "step").animateFloat(
                    initialValue = 1f,
                    targetValue = if (live) 0.45f else 1f,
                    animationSpec = androidx.compose.animation.core.infiniteRepeatable(
                        androidx.compose.animation.core.tween(650, easing = androidx.compose.animation.core.FastOutSlowInEasing),
                        androidx.compose.animation.core.RepeatMode.Reverse,
                    ),
                    label = "pulse",
                )
                Row(
                    Modifier.fillMaxWidth().padding(start = 8.dp).clickable(enabled = more) { expanded = !expanded }.padding(vertical = 3.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    when (status) {
                        "done" -> Icon(Icons.Rounded.Check, contentDescription = null, Modifier.size(16.dp), tint = muted)
                        "error" -> Icon(Icons.Rounded.Close, contentDescription = null, Modifier.size(16.dp), tint = MaterialTheme.colorScheme.error)
                        else -> Icon(stepKind(step).icon, contentDescription = null, Modifier.size(16.dp).graphicsLayer { alpha = pulse }, tint = MaterialTheme.colorScheme.primary)
                    }
                    Text(
                        step.str("title"),
                        Modifier.weight(1f),
                        style = MaterialTheme.typography.bodySmall,
                        color = if (live) MaterialTheme.colorScheme.onSurface else muted,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    if (more) Icon(if (expanded) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore, contentDescription = null, Modifier.size(16.dp), tint = muted)
                }
                if (expanded && step.str("detail").isNotEmpty()) {
                    Text(
                        step.str("detail"),
                        Modifier.padding(start = 40.dp),
                        style = MaterialTheme.typography.bodySmall,
                        color = muted,
                    )
                }
                if (expanded) step.list("items").forEach { item ->
                    Text(
                        item.str("title").ifEmpty { item.str("url") },
                        Modifier.padding(start = 40.dp).clickable {
                            val url = item.str("url")
                            if (url.startsWith("https://") || url.startsWith("http://")) {
                                runCatching { context.startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW, android.net.Uri.parse(url))) }
                            }
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.primary,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
    }
}

private fun stripIcons(text: String): String = text.replace(Regex(":icon\\[[^\\]]*\\]:"), "")

/** A highlighted note (tip, warning, ...) with a coloured edge. */
@Composable
private fun CalloutBlock(block: JSONObject) {
    val accent = when (block.str("kind")) {
        "warning", "caution", "important" -> MaterialTheme.colorScheme.error
        "note", "info" -> MaterialTheme.colorScheme.outline
        else -> MaterialTheme.colorScheme.primary
    }
    Surface(shape = RoundedCornerShape(10.dp), color = MaterialTheme.colorScheme.surfaceContainer, modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(end = 12.dp)) {
            Box(Modifier.padding(vertical = 6.dp).width(3.dp).fillMaxHeight().clip(RoundedCornerShape(2.dp)).background(accent))
            Column(Modifier.padding(start = 10.dp, top = 8.dp, bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                if (block.str("title").isNotEmpty()) Text(block.str("title"), style = MaterialTheme.typography.labelLarge)
                MarkdownText(stripIcons(block.str("text")), Modifier.fillMaxWidth())
            }
        }
    }
}

private val visualPalette = listOf(0xFF7C5CFF, 0xFFE8590C, 0xFF2F9E44, 0xFF1C7ED6, 0xFFD6336C, 0xFFF08C00, 0xFF12B886, 0xFF868E96)
    .map { androidx.compose.ui.graphics.Color(it) }

private fun JSONArray.doubles(): List<Double> = (0 until length()).map { optDouble(it, 0.0) }

/** Draws [text] centred (or right/left aligned) at a point; used for axis labels. */
private fun androidx.compose.ui.graphics.drawscope.DrawScope.label(text: String, x: Float, y: Float, color: Int, align: android.graphics.Paint.Align) {
    val paint = android.graphics.Paint().apply {
        isAntiAlias = true
        this.color = color
        textSize = 11.sp.toPx()
        textAlign = align
    }
    drawIntoCanvas { canvas -> canvas.nativeCanvas.drawText(text, x, y, paint) }
}

/** A formula the core already converted to readable Unicode text. */
@Composable
private fun MathBlock(block: JSONObject) {
    val text = block.str("text").ifEmpty { block.str("tex") }
    Surface(shape = RoundedCornerShape(10.dp), color = MaterialTheme.colorScheme.surfaceContainer, modifier = Modifier.fillMaxWidth()) {
        Text(
            text,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 10.dp),
            textAlign = TextAlign.Center,
            style = MaterialTheme.typography.titleMedium,
        )
    }
}

@Composable
private fun VisualCard(title: String, legend: List<Pair<String, androidx.compose.ui.graphics.Color>>, content: @Composable () -> Unit) {
    Surface(
        shape = RoundedCornerShape(14.dp),
        color = MaterialTheme.colorScheme.surfaceContainer,
        border = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (title.isNotEmpty()) Text(title, style = MaterialTheme.typography.labelLarge)
            content()
            FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                legend.forEach { (name, color) ->
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                        Box(Modifier.size(10.dp).clip(RoundedCornerShape(3.dp)).background(color))
                        Text(name, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

/** A function graph: the core samples the curves, this only maps them onto the canvas. */
@Composable
private fun PlotBlock(block: JSONObject) {
    val x = block.optJSONArray("x")?.doubles() ?: listOf(-10.0, 10.0)
    val y = block.optJSONArray("y")?.doubles() ?: listOf(-10.0, 10.0)
    val curves = block.list("curves")
    val grid = MaterialTheme.colorScheme.outlineVariant
    val axis = MaterialTheme.colorScheme.onSurfaceVariant
    val labelColor = axis.toArgb()
    val legend = curves.mapIndexed { i, c -> c.str("label") to visualPalette[i % visualPalette.size] }
    VisualCard(block.str("title"), legend) {
        androidx.compose.foundation.Canvas(Modifier.fillMaxWidth().height(220.dp)) {
            val left = 40.dp.toPx()
            val right = 10.dp.toPx()
            val top = 8.dp.toPx()
            val bottom = 22.dp.toPx()
            val w = size.width - left - right
            val h = size.height - top - bottom
            if (w <= 0f || h <= 0f || x[1] == x[0] || y[1] == y[0]) return@Canvas
            fun sx(v: Double) = (left + (v - x[0]) / (x[1] - x[0]) * w).toFloat()
            fun sy(v: Double) = (top + h - (v - y[0]) / (y[1] - y[0]) * h).toFloat()
            fun fmt(v: Double) = if (v == Math.rint(v)) v.toLong().toString() else v.toString()
            block.optJSONArray("xticks")?.doubles()?.forEach { t ->
                drawLine(grid, androidx.compose.ui.geometry.Offset(sx(t), top), androidx.compose.ui.geometry.Offset(sx(t), top + h), 1f)
                label(fmt(t), sx(t), top + h + 15.dp.toPx(), labelColor, android.graphics.Paint.Align.CENTER)
            }
            block.optJSONArray("yticks")?.doubles()?.forEach { t ->
                drawLine(grid, androidx.compose.ui.geometry.Offset(left, sy(t)), androidx.compose.ui.geometry.Offset(left + w, sy(t)), 1f)
                label(fmt(t), left - 5.dp.toPx(), sy(t) + 4.dp.toPx(), labelColor, android.graphics.Paint.Align.RIGHT)
            }
            if (x[0] <= 0 && x[1] >= 0) drawLine(axis, androidx.compose.ui.geometry.Offset(sx(0.0), top), androidx.compose.ui.geometry.Offset(sx(0.0), top + h), 1.5f)
            if (y[0] <= 0 && y[1] >= 0) drawLine(axis, androidx.compose.ui.geometry.Offset(left, sy(0.0)), androidx.compose.ui.geometry.Offset(left + w, sy(0.0)), 1.5f)
            clipRect(left, top, left + w, top + h) {
                curves.forEachIndexed { i, c ->
                    val color = visualPalette[i % visualPalette.size]
                    when (c.str("kind")) {
                        "line" -> c.optJSONArray("lines")?.let { lines ->
                            for (l in 0 until lines.length()) {
                                val pts = lines.optJSONArray(l) ?: continue
                                val path = androidx.compose.ui.graphics.Path()
                                for (k in 0 until pts.length()) {
                                    val pt = pts.optJSONArray(k) ?: continue
                                    val px = sx(pt.optDouble(0))
                                    val py = sy(pt.optDouble(1))
                                    if (k == 0) path.moveTo(px, py) else path.lineTo(px, py)
                                }
                                drawPath(path, color, style = androidx.compose.ui.graphics.drawscope.Stroke(width = 2.dp.toPx(), join = androidx.compose.ui.graphics.StrokeJoin.Round))
                            }
                        }
                        "vline" -> drawLine(color, androidx.compose.ui.geometry.Offset(sx(c.optDouble("x")), top), androidx.compose.ui.geometry.Offset(sx(c.optDouble("x")), top + h), 2.dp.toPx())
                        "points" -> c.optJSONArray("points")?.let { pts ->
                            for (k in 0 until pts.length()) {
                                val pt = pts.optJSONArray(k) ?: continue
                                drawCircle(color, 4.dp.toPx(), androidx.compose.ui.geometry.Offset(sx(pt.optDouble(0)), sy(pt.optDouble(1))))
                            }
                        }
                    }
                }
            }
        }
        block.optJSONArray("errors")?.let { errors ->
            for (i in 0 until errors.length()) Text(errors.optString(i), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
        }
    }
}

/** A bar, line or pie chart whose axis range and ticks were chosen by the core. */
@Composable
private fun ChartBlock(block: JSONObject) {
    val pie = block.str("kind") == "pie"
    val labels = block.optJSONArray("labels")?.let { a -> (0 until a.length()).map { a.optString(it) } } ?: emptyList()
    val series = block.list("series")
    val grid = MaterialTheme.colorScheme.outlineVariant
    val labelColor = MaterialTheme.colorScheme.onSurfaceVariant.toArgb()
    val legend = if (pie) labels.mapIndexed { i, n -> n to visualPalette[i % visualPalette.size] }
    else series.mapIndexed { i, s -> s.str("name") to visualPalette[i % visualPalette.size] }
    VisualCard(block.str("title"), legend) {
        androidx.compose.foundation.Canvas(Modifier.fillMaxWidth().height(if (pie) 220.dp else 200.dp)) {
            if (labels.isEmpty() || series.isEmpty()) return@Canvas
            if (pie) {
                val data = series[0].optJSONArray("data")?.doubles() ?: return@Canvas
                val total = data.sum()
                if (total <= 0.0) return@Canvas
                val d = minOf(size.width, size.height) - 16.dp.toPx()
                var start = -90f
                data.forEachIndexed { i, v ->
                    val sweep = (v / total * 360.0).toFloat()
                    drawArc(
                        visualPalette[i % visualPalette.size], start, sweep, true,
                        topLeft = androidx.compose.ui.geometry.Offset((size.width - d) / 2, (size.height - d) / 2),
                        size = androidx.compose.ui.geometry.Size(d, d),
                    )
                    start += sweep
                }
                return@Canvas
            }
            val lo = block.optDouble("min", 0.0)
            val hi = block.optDouble("max", 1.0)
            if (hi == lo) return@Canvas
            val left = 40.dp.toPx()
            val top = 8.dp.toPx()
            val w = size.width - left - 10.dp.toPx()
            val h = size.height - top - 22.dp.toPx()
            if (w <= 0f || h <= 0f) return@Canvas
            fun sy(v: Double) = (top + h - (v - lo) / (hi - lo) * h).toFloat()
            val band = w / labels.size
            block.optJSONArray("ticks")?.doubles()?.forEach { t ->
                drawLine(grid, androidx.compose.ui.geometry.Offset(left, sy(t)), androidx.compose.ui.geometry.Offset(left + w, sy(t)), 1f)
                label(if (t == Math.rint(t)) t.toLong().toString() else t.toString(), left - 5.dp.toPx(), sy(t) + 4.dp.toPx(), labelColor, android.graphics.Paint.Align.RIGHT)
            }
            labels.forEachIndexed { i, text ->
                label(if (text.length > 8) text.take(7) + "…" else text, left + band * (i + 0.5f), top + h + 15.dp.toPx(), labelColor, android.graphics.Paint.Align.CENTER)
            }
            series.forEachIndexed { si, s ->
                val color = visualPalette[si % visualPalette.size]
                val data = s.optJSONArray("data")?.doubles() ?: return@forEachIndexed
                if (block.str("kind") == "bar") {
                    val bw = band * 0.8f / series.size
                    data.forEachIndexed { i, v ->
                        val y0 = sy(0.0)
                        val y1 = sy(v)
                        drawRect(
                            color,
                            topLeft = androidx.compose.ui.geometry.Offset(left + band * i + band * 0.1f + bw * si, minOf(y0, y1)),
                            size = androidx.compose.ui.geometry.Size(bw, kotlin.math.abs(y1 - y0)),
                        )
                    }
                } else {
                    val path = androidx.compose.ui.graphics.Path()
                    data.forEachIndexed { i, v ->
                        val px = left + band * (i + 0.5f)
                        if (i == 0) path.moveTo(px, sy(v)) else path.lineTo(px, sy(v))
                    }
                    drawPath(path, color, style = androidx.compose.ui.graphics.drawscope.Stroke(width = 2.dp.toPx()))
                    data.forEachIndexed { i, v -> drawCircle(color, 3.5.dp.toPx(), androidx.compose.ui.geometry.Offset(left + band * (i + 0.5f), sy(v))) }
                }
            }
        }
    }
}

/** A ready-to-send draft: variant tabs, subject, body and a copy button. */
@Composable
private fun DraftBlock(block: JSONObject, strings: JSONObject) {
    val variants = block.list("variants")
    var pick by remember { mutableStateOf(0) }
    val variant = variants.getOrNull(pick) ?: return
    val clipboard = LocalClipboardManager.current
    Surface(
        shape = RoundedCornerShape(14.dp),
        color = MaterialTheme.colorScheme.surfaceContainer,
        border = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (block.str("title").isNotEmpty()) Text(block.str("title"), style = MaterialTheme.typography.labelLarge)
            if (variants.size > 1) {
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    variants.forEachIndexed { i, v ->
                        FilterChip(selected = i == pick, onClick = { pick = i }, label = { Text(v.str("label").ifEmpty { ('A' + i).toString() }) })
                    }
                }
            }
            if (variant.str("subject").isNotEmpty()) {
                Text("${strings.str("subject").ifEmpty { "Subject" }}: ${variant.str("subject")}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            androidx.compose.material3.HorizontalDivider()
            Text(variant.str("body"), style = MaterialTheme.typography.bodyMedium)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                FilledTonalButton(onClick = { clipboard.setText(AnnotatedString(variant.str("body"))) }) { Text(strings.str("copy").ifEmpty { "Copy" }) }
            }
        }
    }
}

/** One collapsible section of the details card (environment, context, tools, resources). */
@Composable
private fun InspectorSection(sec: JSONObject) {
    var open by remember { mutableStateOf(sec.optBoolean("open", true)) }
    val context = LocalContext.current
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Row(Modifier.fillMaxWidth().clickable { open = !open }.padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(sec.str("title"), Modifier.weight(1f), style = MaterialTheme.typography.labelLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Icon(if (open) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore, contentDescription = null, Modifier.size(18.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (open) {
            sec.obj("bar")?.let { bar ->
                val segs = bar.list("segments")
                val total = segs.sumOf { it.optDouble("value", 0.0) }.coerceAtLeast(1.0)
                Row(Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp)), horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                    segs.forEachIndexed { i, x ->
                        val w = (x.optDouble("value", 0.0) / total).toFloat().coerceAtLeast(0.01f)
                        Box(Modifier.weight(w).fillMaxHeight().background(if (i == 0) MaterialTheme.colorScheme.primary else if (i == 1) MaterialTheme.colorScheme.tertiary else MaterialTheme.colorScheme.outlineVariant))
                    }
                }
                if (bar.str("label").isNotEmpty()) Text(bar.str("label"), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            sec.list("rows").filter { it.str("label").isNotEmpty() }.forEach { r ->
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (r.str("status").isNotEmpty()) {
                        Box(Modifier.size(6.dp).clip(RoundedCornerShape(3.dp)).background(
                            if (r.str("status") == "error") MaterialTheme.colorScheme.error
                            else if (r.str("status") == "done") MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.outline
                        ))
                    }
                    Text(r.str("label"), Modifier.weight(1f), style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (!r.isNull("value")) Text(r.str("value"), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.widthIn(max = 90.dp))
                }
            }
            sec.list("links").forEach { r ->
                val url = r.str("url")
                Text(
                    r.str("title").ifEmpty { url },
                    Modifier.clickable(enabled = url.startsWith("http")) {
                        runCatching { context.startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW, android.net.Uri.parse(url))) }
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
private fun Composer(composer: JSONObject, files: List<JSONObject>, prefs: JSONObject?, strings: JSONObject, act: Act) {
    var input by remember { mutableStateOf("") }
    val busy = composer.optBoolean("busy")
    val enterSends = prefs?.optBoolean("general.enter_to_send", true) ?: true
    val send = {
        val text = input.trim()
        val action = composer.obj("sendAction")
        if (text.isNotEmpty() && !busy && action != null) {
            act(action.withField("text", text))
            input = ""
        }
    }
    val context = LocalContext.current
    val attach = composer.obj("attach")
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null && attach != null) {
            val resolver = context.contentResolver
            val name = resolver.query(uri, arrayOf(android.provider.OpenableColumns.DISPLAY_NAME), null, null, null)
                ?.use { if (it.moveToFirst()) it.getString(0) else null } ?: "file.txt"
            val type = resolver.getType(uri).orEmpty()
            if (type.startsWith("image/")) {
                val data = shrinkPicture(context, uri)
                if (data == null) {
                    android.widget.Toast.makeText(context, "That picture could not be prepared.", android.widget.Toast.LENGTH_SHORT).show()
                } else {
                    act(JSONObject().put("type", "attach_image").put("name", name).put("mime", "image/jpeg").put("data", data))
                }
                return@rememberLauncherForActivityResult
            }
            val text = runCatching {
                resolver.openInputStream(uri)?.use { it.readBytes() }?.takeIf { it.size <= 2 * 1024 * 1024 }?.let {
                    Charsets.UTF_8.newDecoder()
                        .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
                        .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT)
                        .decode(java.nio.ByteBuffer.wrap(it)).toString()
                }
            }.getOrNull()
            if (text == null) {
                android.widget.Toast.makeText(context, "Only text files up to 2 MB can be attached.", android.widget.Toast.LENGTH_SHORT).show()
            } else {
                act(JSONObject().put("type", attach.str("action")).put("name", name).put("text", text))
            }
        }
    }
    Column(Modifier.padding(horizontal = 12.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (files.isNotEmpty()) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                files.forEach { file ->
                    InputChip(
                        selected = false,
                        onClick = { act.send(file.obj("remove")?.obj("action")) },
                        label = { Text("${file.str("name")} · ${file.str("subtitle")}  ✕", maxLines = 1, overflow = TextOverflow.Ellipsis) },
                    )
                }
            }
        }
        val matches = if (Regex("^/\\S*$").matches(input)) {
            composer.list("commands").filter { it.str("name").startsWith(input.lowercase()) }
        } else emptyList()
        if (matches.isNotEmpty()) {
            Card(Modifier.fillMaxWidth()) {
                matches.forEach { c ->
                    Column(
                        Modifier.fillMaxWidth().clickable {
                            if (c.str("hint").isNotEmpty()) input = c.str("name") + " "
                            else if (!busy) {
                                composer.obj("sendAction")?.let { act(it.withField("text", c.str("name"))) }
                                input = ""
                            }
                        }.padding(horizontal = 16.dp, vertical = 8.dp),
                    ) {
                        Text(c.str("name") + if (c.str("hint").isNotEmpty()) " ${c.str("hint")}" else "", style = MaterialTheme.typography.titleSmall)
                        Text(c.str("label"), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
        Row(
            Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceContainerHigh, RoundedCornerShape(24.dp)).padding(start = 4.dp, end = 6.dp, top = 4.dp, bottom = 4.dp),
            verticalAlignment = Alignment.Bottom,
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            if (attach != null) {
                IconButton(onClick = { picker.launch(arrayOf("image/*", "text/*", "application/json", "application/xml", "application/x-sh", "application/octet-stream")) }, Modifier.size(40.dp)) {
                    Icon(Icons.Rounded.AttachFile, contentDescription = attach.str("label"))
                }
            }
            Box(Modifier.weight(1f).heightIn(min = 40.dp).padding(vertical = 10.dp), contentAlignment = Alignment.CenterStart) {
                BasicTextField(
                    value = input,
                    onValueChange = { input = it },
                    modifier = Modifier.fillMaxWidth().onPreviewKeyEvent { event ->
                        // Hardware keyboards: Enter sends (Shift+Enter newline), or the reverse.
                        if (event.type == KeyEventType.KeyDown && event.key == Key.Enter && enterSends != event.isShiftPressed) {
                            send()
                            true
                        } else {
                            false
                        }
                    },
                    textStyle = MaterialTheme.typography.bodyLarge.copy(color = MaterialTheme.colorScheme.onSurface),
                    maxLines = 6,
                    cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                    decorationBox = { inner ->
                        if (input.isEmpty()) Text(composer.str("placeholder"), style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        inner()
                    },
                )
            }
            FilledIconButton(onClick = { if (busy) act.send(composer.obj("stopAction")) else send() }, Modifier.size(36.dp)) {
                Icon(if (busy) Icons.Rounded.Stop else Icons.AutoMirrored.Rounded.Send, contentDescription = if (busy) strings.str("stop").ifEmpty { "Stop" } else strings.str("send").ifEmpty { "Send" })
            }
        }
        // Controls under the input: permission, web search on the left; model, thinking, sub-agents on the right.
        val toolbar = composer.list("toolbar")
        FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(2.dp), verticalArrangement = Arrangement.spacedBy(0.dp)) {
            (toolbar.filter { it.str("align") != "end" } + toolbar.filter { it.str("align") == "end" }).forEach { ControlChip(it, act) }
        }
    }
}


/** Downscale a picture to at most 1568 px and return base64 JPEG (no wrapping), or null. */
private fun shrinkPicture(context: android.content.Context, uri: android.net.Uri): String? = runCatching {
    val resolver = context.contentResolver
    val bounds = android.graphics.BitmapFactory.Options().apply { inJustDecodeBounds = true }
    resolver.openInputStream(uri)?.use { android.graphics.BitmapFactory.decodeStream(it, null, bounds) }
    var sample = 1
    while (maxOf(bounds.outWidth, bounds.outHeight) / sample > 3136) sample *= 2
    val options = android.graphics.BitmapFactory.Options().apply { inSampleSize = sample }
    val decoded = resolver.openInputStream(uri)?.use { android.graphics.BitmapFactory.decodeStream(it, null, options) } ?: return null
    val scale = minOf(1f, 1568f / maxOf(decoded.width, decoded.height))
    val bitmap = if (scale < 1f) android.graphics.Bitmap.createScaledBitmap(decoded, (decoded.width * scale).toInt(), (decoded.height * scale).toInt(), true) else decoded
    for (quality in intArrayOf(85, 70, 55, 40)) {
        val out = java.io.ByteArrayOutputStream()
        bitmap.compress(android.graphics.Bitmap.CompressFormat.JPEG, quality, out)
        val data = android.util.Base64.encodeToString(out.toByteArray(), android.util.Base64.NO_WRAP)
        if (data.length <= 1_800_000) return data
    }
    null
}.getOrNull()


// ---------- Plugin store (page.kind = "store") ----------

private fun withField(action: JSONObject, field: String, value: String): JSONObject =
    JSONObject(action.toString()).put(field, value)

private fun glyphIcon(name: String) = when (name) {
    "account_tree" -> Icons.Rounded.AccountTree
    "language" -> Icons.Rounded.Language
    "description" -> Icons.Rounded.Description
    "search" -> Icons.Rounded.Search
    "work" -> Icons.Rounded.Work
    "edit" -> Icons.Rounded.Edit
    "cloud" -> Icons.Rounded.Cloud
    "lightbulb" -> Icons.Rounded.Lightbulb
    else -> Icons.Rounded.AutoAwesome
}

/** The app mark: a brand glyph (24x24 `svg` path), a named glyph, or a letter tile. */
@Composable
private fun AppIcon(icon: JSONObject?, label: String, tile: androidx.compose.ui.unit.Dp = 44.dp) {
    val svg = icon?.str("svg").orEmpty()
    val glyph = icon?.str("glyph").orEmpty()
    val tint = icon?.str("color").orEmpty().let { c ->
        runCatching { androidx.compose.ui.graphics.Color(android.graphics.Color.parseColor(c)) }.getOrNull()
    } ?: MaterialTheme.colorScheme.onSurface
    val letterBg = androidx.compose.ui.graphics.Color.hsl(((label.firstOrNull()?.code ?: 0) * 37 % 360).toFloat(), 0.55f, 0.42f)
    Box(
        Modifier.size(tile).clip(RoundedCornerShape(tile * 0.28f))
            .background(if (svg.isNotEmpty() || glyph.isNotEmpty()) MaterialTheme.colorScheme.surfaceContainerHighest else letterBg),
        contentAlignment = Alignment.Center,
    ) {
        when {
            svg.isNotEmpty() -> {
                val path = remember(svg) {
                    runCatching { androidx.compose.ui.graphics.vector.PathParser().parsePathString(svg).toPath() }.getOrNull()
                }
                if (path != null) androidx.compose.foundation.Canvas(Modifier.size(tile * 0.56f)) {
                    val k = size.width / 24f
                    scale(k, k, androidx.compose.ui.geometry.Offset.Zero) {
                        drawPath(path, tint)
                    }
                }
            }
            glyph.isNotEmpty() -> Icon(glyphIcon(glyph), contentDescription = null, tint = tint, modifier = Modifier.size(tile * 0.5f))
            else -> Text(
                label.firstOrNull { it.isLetterOrDigit() }?.uppercase() ?: "?",
                color = androidx.compose.ui.graphics.Color.White,
                style = MaterialTheme.typography.titleMedium,
            )
        }
    }
}

@Composable
private fun StorePage(page: JSONObject, act: Act) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val search = page.obj("search")
    var query by remember(search?.str("value")) { mutableStateOf(search?.str("value").orEmpty()) }
    val run: (JSONObject?) -> Unit = { action ->
        if (action != null && action.str("type") == "open_link") {
            val url = action.str("url")
            if (url.startsWith("https://"))
                runCatching { context.startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW, android.net.Uri.parse(url))) }
        } else act.send(action)
    }
    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(page.str("title"), style = MaterialTheme.typography.headlineMedium)
                if (page.optBoolean("loading")) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp)
            }
        }
        if (search != null) item {
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                placeholder = { Text(search.str("placeholder")) },
                leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
                shape = RoundedCornerShape(28.dp),
                keyboardOptions = KeyboardOptions(imeAction = androidx.compose.ui.text.input.ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = {
                    act.send(withField(search.obj("action") ?: JSONObject(), search.str("field"), query))
                }),
            )
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.horizontalScroll(rememberScrollState())) {
                page.list("tabs").forEach { t ->
                    FilterChip(selected = t.optBoolean("selected"), onClick = { run(t.obj("action")) }, label = { Text(t.str("label")) })
                }
            }
        }
        if (page.list("filters").isNotEmpty()) item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.horizontalScroll(rememberScrollState())) {
                page.list("filters").forEach { f ->
                    InputChip(selected = f.optBoolean("selected"), onClick = { run(f.obj("action")) }, label = { Text(f.str("label")) })
                }
            }
        }
        page.list("sections").forEach { sec ->
            item { Text(sec.str("title"), style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            val cards = sec.list("cards")
            if (sec.has("cards") && cards.isEmpty() && sec.str("empty").isNotEmpty())
                item { Text(sec.str("empty"), color = MaterialTheme.colorScheme.onSurfaceVariant) }
            items(cards) { card ->
                Card(Modifier.fillMaxWidth()) {
                    Row(Modifier.padding(14.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        AppIcon(card.obj("icon"), card.str("title"))
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(card.str("title"), Modifier.weight(1f), style = MaterialTheme.typography.titleSmall)
                                card.obj("switch")?.let { sw ->
                                    androidx.compose.material3.Switch(checked = sw.optBoolean("on"), onCheckedChange = { run(sw.obj("action")) })
                                }
                            }
                            Text(card.str("publisher"), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(card.str("subtitle"), style = MaterialTheme.typography.bodySmall, maxLines = 3, overflow = TextOverflow.Ellipsis)
                            card.str("detail").takeIf { it.isNotEmpty() }?.let {
                                Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            val badges = (0 until (card.optJSONArray("badges")?.length() ?: 0)).map { card.optJSONArray("badges")!!.optString(it) } +
                                if (card.str("state") == "installed") listOf("✓ Installed") else emptyList()
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                val tone = card.str("tone")
                                if (tone.isNotEmpty()) Box(
                                    Modifier.size(8.dp).clip(RoundedCornerShape(50)).background(
                                        when (tone) {
                                            "ok" -> androidx.compose.ui.graphics.Color(0xFF2E7D32)
                                            "error" -> MaterialTheme.colorScheme.error
                                            else -> androidx.compose.ui.graphics.Color(0xFFB26A00)
                                        },
                                    ),
                                )
                                Text(badges.joinToString("  ·  "), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                            }
                            val actions = card.list("actions")
                            if (actions.isNotEmpty()) FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.End)) {
                                actions.forEach { a ->
                                    val click = { run(a.obj("action")) }
                                    if (a.str("style") == "primary") Button(onClick = click) { Text(a.str("label")) }
                                    else FilledTonalButton(onClick = click) { Text(a.str("label")) }
                                }
                            }
                        }
                    }
                }
            }
            items(sec.list("forms")) { form ->
                var value by remember { mutableStateOf("") }
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            AppIcon(form.obj("icon"), form.str("title"), 36.dp)
                            Text(form.str("title"), style = MaterialTheme.typography.titleSmall)
                        }
                        Text(form.str("text"), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        OutlinedTextField(value = value, onValueChange = { value = it }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                            placeholder = { Text(form.str("placeholder")) })
                        Button(enabled = value.isNotBlank(), onClick = {
                            act.send(withField(form.obj("action") ?: JSONObject(), form.str("field"), value.trim()))
                            value = ""
                        }) { Text(form.str("button")) }
                    }
                }
            }
            items(sec.list("links")) { link ->
                ListItem(
                    headlineContent = { Text(link.str("title")) },
                    supportingContent = { Text(link.str("subtitle")) },
                    modifier = Modifier.clickable { run(JSONObject().put("type", "open_link").put("url", link.str("url"))) },
                )
            }
        }
    }
}

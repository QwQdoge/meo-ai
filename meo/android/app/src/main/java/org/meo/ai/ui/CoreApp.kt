package org.meo.ai.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
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
import androidx.compose.material.icons.Icons
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
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import org.meo.ai.R

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
    val navigation = view.list("navigation")
    val page = view.obj("page") ?: JSONObject()
    val notice = view.obj("notice")

    view.obj("dialog")?.let { CoreDialog(it, act) }

    BoxWithConstraints(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        val wide = maxWidth >= 840.dp
        Row(Modifier.fillMaxSize()) {
            if (wide && navigation.isNotEmpty()) {
                NavigationRail(containerColor = MaterialTheme.colorScheme.surfaceContainer) {
                    navigation.forEach { item ->
                        NavigationRailItem(
                            selected = item.optBoolean("selected"),
                            onClick = { act.send(item.obj("action")) },
                            icon = { Icon(navigationIcon(item.str("symbol")), contentDescription = null) },
                            label = { Text(item.str("label")) },
                        )
                    }
                }
            }
            Scaffold(
                modifier = Modifier.weight(1f),
                containerColor = MaterialTheme.colorScheme.background,
                bottomBar = {
                    if (!wide && navigation.isNotEmpty()) {
                        NavigationBar {
                            navigation.forEach { item ->
                                NavigationBarItem(
                                    selected = item.optBoolean("selected"),
                                    onClick = { act.send(item.obj("action")) },
                                    icon = { Icon(navigationIcon(item.str("symbol")), contentDescription = null) },
                                    label = { Text(item.str("label"), maxLines = 1, overflow = TextOverflow.Ellipsis) },
                                )
                            }
                        }
                    }
                },
            ) { padding ->
                Column(Modifier.padding(padding).fillMaxSize()) {
                    if (notice != null) {
                        Banner(
                            text = notice.str("text"),
                            error = notice.str("kind") == "error",
                            actionLabel = strings.str("dismiss").ifEmpty { "Dismiss" },
                            onAction = { act.send(notice.obj("action")) },
                        )
                    }
                    if (!view.optBoolean("online", true)) {
                        Banner(text = strings.str("offline").ifEmpty { "Offline — showing saved data" }, error = false)
                    }
                    Box(Modifier.weight(1f).fillMaxWidth()) {
                        when (page.str("kind")) {
                            "sign_in" -> SignInPage(page, act)
                            "conversation" -> ConversationPage(page, view.obj("prefs"), strings, wide, act)
                            "list" -> ListPage(page, act)
                            "settings" -> SettingsPage(page, act)
                            else -> UnavailablePage(page, act)
                        }
                    }
                }
            }
        }
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
        if (page.optBoolean("busy")) CircularProgressIndicator()
        page.list("actions").forEach { ActionButton(it, act) }
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
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(24.dp),
    ) {
        Text(page.str("title"), style = MaterialTheme.typography.headlineMedium)
        page.list("sections").forEach { section ->
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(section.str("label"), style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary)
                section.list("items").forEach { SettingControl(it, act) }
            }
        }
    }
}

private fun setting(item: JSONObject, value: Any?): JSONObject =
    JSONObject().put("type", "set_setting").put("binding", item.str("binding")).put("value", value)

@Composable
private fun SettingControl(item: JSONObject, act: Act, modifier: Modifier = Modifier.fillMaxWidth()) {
    when (item.str("kind")) {
        "toggle" -> Row(modifier, verticalAlignment = Alignment.CenterVertically) {
            Text(item.str("label"), Modifier.weight(1f))
            Switch(checked = item.optBoolean("value"), onCheckedChange = { act(setting(item, it)) })
        }
        "select" -> SelectControl(item, act, modifier)
        "text" -> TextControl(item, act, modifier)
        "info" -> Row(modifier, verticalAlignment = Alignment.CenterVertically) {
            Text(item.str("label"), Modifier.weight(1f))
            Text(item.str("value"), color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        "button" -> ActionButton(item, act, modifier)
    }
}

@Composable
private fun SelectControl(item: JSONObject, act: Act, modifier: Modifier) {
    var open by remember { mutableStateOf(false) }
    val options = item.list("options")
    val current = options.firstOrNull { it.str("value") == item.str("value") }
    Column(modifier) {
        Text(item.str("label"), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Box {
            OutlinedButton(onClick = { open = true }, enabled = options.isNotEmpty(), modifier = Modifier.fillMaxWidth()) {
                Text(current?.str("label") ?: "—", Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
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

@Composable
private fun ConversationPage(page: JSONObject, prefs: JSONObject?, strings: JSONObject, wide: Boolean, act: Act) {
    val sidebar = page.obj("sidebar") ?: JSONObject()
    if (wide) {
        Row(Modifier.fillMaxSize()) {
            Sidebar(sidebar, act, Modifier.width(280.dp).fillMaxHeight())
            Box(Modifier.fillMaxHeight().width(1.dp).background(MaterialTheme.colorScheme.outlineVariant))
            ChatPane(page, prefs, strings, onMenu = null, act = act, modifier = Modifier.weight(1f))
        }
    } else {
        val drawer = rememberDrawerState(DrawerValue.Closed)
        val scope = rememberCoroutineScope()
        ModalNavigationDrawer(
            drawerState = drawer,
            drawerContent = {
                ModalDrawerSheet {
                    Sidebar(sidebar, { action ->
                        scope.launch { drawer.close() }
                        act(action)
                    }, Modifier.fillMaxHeight())
                }
            },
        ) {
            ChatPane(page, prefs, strings, onMenu = { scope.launch { drawer.open() } }, act = act, modifier = Modifier.fillMaxSize())
        }
    }
}

@Composable
private fun Sidebar(sidebar: JSONObject, act: Act, modifier: Modifier) {
    Column(modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        sidebar.list("actions").forEach { ActionButton(it, act, Modifier.fillMaxWidth()) }
        sidebar.obj("search")?.let { SearchField(it, act) }
        val tabs = sidebar.list("tabs")
        if (tabs.isNotEmpty()) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                tabs.forEach { tab ->
                    FilterChip(
                        selected = tab.optBoolean("selected"),
                        onClick = { act.send(tab.obj("action")) },
                        label = { Text(tab.str("label")) },
                    )
                }
            }
        }
        Text(sidebar.str("title"), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
        LazyColumn(Modifier.weight(1f)) {
            items(sidebar.list("items")) { item ->
                val selected = item.optBoolean("selected")
                var menuOpen by remember { mutableStateOf(false) }
                Surface(
                    onClick = { act.send(item.obj("action")) },
                    shape = RoundedCornerShape(16.dp),
                    color = if (selected) MaterialTheme.colorScheme.secondaryContainer else androidx.compose.ui.graphics.Color.Transparent,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Row(Modifier.padding(start = 16.dp, top = 4.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f).padding(vertical = 6.dp)) {
                            Text(item.str("title"), maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(
                                item.str("subtitle"),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
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
                                            onClick = {
                                                menuOpen = false
                                                act.send(entry.obj("action"))
                                            },
                                        )
                                    }
                                }
                            }
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
    OutlinedTextField(
        value = text,
        onValueChange = { text = it },
        modifier = Modifier.fillMaxWidth(),
        singleLine = true,
        leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
        placeholder = { Text(search.str("placeholder")) },
        shape = RoundedCornerShape(24.dp),
    )
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
                style = MaterialTheme.typography.titleLarge,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Box(Modifier.weight(1f).fillMaxWidth()) {
            val empty = page.obj("empty")
            if (empty != null) {
                Column(
                    Modifier.align(Alignment.Center).padding(32.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(empty.str("title"), style = MaterialTheme.typography.headlineSmall, textAlign = TextAlign.Center)
                    Text(
                        empty.str("text"),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        textAlign = TextAlign.Center,
                    )
                }
            }
            LazyColumn(
                Modifier.fillMaxSize(),
                state = listState,
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(messages) { MessageBubble(it, strings, act) }
            }
        }
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
        Composer(composer, prefs, strings, act)
    }
}

@Composable
private fun MessageBubble(message: JSONObject, strings: JSONObject, act: Act) {
    val mine = message.str("role") == "user"
    val streaming = message.optBoolean("streaming")
    val text = message.str("text") + if (streaming) " ▍" else ""
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
                RichBlockRenderer(blocksJson = markdownBlocks(text), modifier = Modifier.fillMaxWidth())
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

@Composable
private fun Composer(composer: JSONObject, prefs: JSONObject?, strings: JSONObject, act: Act) {
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
    Column(Modifier.padding(horizontal = 12.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        composer.list("toolbar").forEach { SettingControl(it, act) }
        Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = input,
                onValueChange = { input = it },
                modifier = Modifier.weight(1f).onPreviewKeyEvent { event ->
                    // Hardware keyboards: Enter sends (Shift+Enter newline), or the reverse.
                    if (event.type == KeyEventType.KeyDown && event.key == Key.Enter && enterSends != event.isShiftPressed) {
                        send()
                        true
                    } else {
                        false
                    }
                },
                placeholder = { Text(composer.str("placeholder")) },
                maxLines = 6,
                shape = RoundedCornerShape(24.dp),
            )
            FilledIconButton(onClick = { if (busy) act.send(composer.obj("stopAction")) else send() }) {
                Icon(if (busy) Icons.Rounded.Stop else Icons.AutoMirrored.Rounded.Send, contentDescription = if (busy) strings.str("stop").ifEmpty { "Stop" } else strings.str("send").ifEmpty { "Send" })
            }
        }
    }
}

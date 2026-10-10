import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtCore
import MeoUI 1.0

ApplicationWindow {
    id: window
    objectName: "meoAiMainWindow"
    width: 1440
    height: 900
    minimumWidth: 620
    minimumHeight: 500
    visible: true
    title: qsTr("Meo AI")
    color: MeoTheme.surfaceContainer
    readonly property real scale: MeoTheme.globalScale
    readonly property bool compact: width < 760 * scale
    readonly property bool showSidebar: width >= 1120 * scale
    readonly property bool showDock: width >= 1280 * scale && inspectorOpen && messages.count > 0
    readonly property real pageMargin: compact ? 18 * scale : 28 * scale
    readonly property real contentMaxWidth: 840 * scale
    readonly property real composerMaxWidth: 840 * scale
    readonly property bool previewMode: typeof uiPreview !== "undefined" && uiPreview
    property bool sidebarHidden: layoutPreferences.sidebarHidden
    property bool inspectorOpen: layoutPreferences.inspectorOpen
    property bool inspectorPinned: false
    property int inspectorTab: 0
    property var inspectedMetadata: ({})
    property var toolEvents: []
    property var currentToolEvents: []
    property string pendingToolDisplay: ""
    readonly property string conversationTitle: {
        for (let i = 0; i < messages.count; ++i) {
            if (messages.get(i).speaker === "user") {
                const text = messages.get(i).body.replace(/\s+/g, " ")
                return text.length > 48 ? text.slice(0, 48) + "…" : text
            }
        }
        return qsTr("New conversation")
    }
    readonly property string selectedModelLabel: {
        for (let i = 0; i < agent.models.length; ++i) {
            if (agent.models[i].selected === true)
                return String(agent.models[i].label || agent.models[i].model_id || "")
        }
        return ""
    }
    function openInspector(tab) {
        inspectorTab = tab
        inspectorOpen = true
        if (width < 1280 * scale || messages.count === 0) inspectorOverlay.open()
    }
    function matchingMessages(query) {
        let count = 0
        for (let i = 0; i < messages.count; ++i)
            if (messages.get(i).body.toLowerCase().indexOf(query.toLowerCase()) >= 0) ++count
        return count
    }
    Component.onCompleted: if (agent.serviceMode && !previewMode) agent.refreshServiceMetadata()
    onShowDockChanged: if (showDock) inspectorOverlay.close()
    onSidebarHiddenChanged: layoutPreferences.sidebarHidden = sidebarHidden
    onInspectorOpenChanged: layoutPreferences.inspectorOpen = inspectorOpen
    Settings {
        id: layoutPreferences
        category: "NativeLayout"
        property real sidebarWidth: 248
        property real detailsWidth: 340
        property bool sidebarHidden: false
        property bool inspectorOpen: true
    }

    function submit(text) {
        const value = String(text).trim()
        if (!value.length || agent.busy || agent.actionBusy || agent.options.length)
            return
        agent.send(value)
        composer.text = ""
    }

    function metaNumber(value) {
        return typeof value === "number" && isFinite(value) ? value : null
    }

    function formatTokens(value) {
        const n = metaNumber(value)
        if (n === null)
            return ""
        if (n >= 1000000)
            return (n / 1000000).toFixed(n >= 10000000 ? 0 : 1) + "M"
        if (n >= 1000)
            return (n / 1000).toFixed(n >= 10000 ? 0 : 1) + "k"
        return String(Math.round(n))
    }

    function formatDuration(value) {
        const n = metaNumber(value)
        if (n === null)
            return ""
        if (n >= 1000)
            return (n / 1000).toFixed(n >= 10000 ? 1 : 2) + " s"
        return Math.round(n) + " ms"
    }

    function responseMetaSummary(meta) {
        if (!meta || typeof meta !== "object")
            return qsTr("Response details")
        const parts = []
        const timing = meta.timing || {}
        const usage = meta.usage || {}
        const context = meta.context || {}
        const activity = meta.activity || {}
        const reasoning = meta.reasoning || {}
        if (timing.total_ms !== undefined)
            parts.push(formatDuration(timing.total_ms))
        if (usage.total_tokens !== undefined)
            parts.push(qsTr("%1 tokens").arg(formatTokens(usage.total_tokens)))
        if (context.percent_used !== undefined)
            parts.push(qsTr("%1% context").arg(Number(context.percent_used).toFixed(1)))
        if (activity.search || activity.web || activity.retrieval)
            parts.push(qsTr("Search"))
        if (activity.memory)
            parts.push(qsTr("Memory"))
        if (activity.tools)
            parts.push(qsTr("Tools"))
        if (activity.mcp)
            parts.push(qsTr("MCP"))
        if (reasoning.available === true)
            parts.push(qsTr("Reasoning"))
        return parts.length ? parts.join(" · ") : qsTr("Response details")
    }

    function cardIndexById(cardId) {
        const wanted = String(cardId || "")
        if (!wanted.length)
            return -1
        for (let i = 0; i < presentationCards.count; ++i) {
            if (String(presentationCards.get(i).cardId || "") === wanted)
                return i
        }
        return -1
    }

    function upsertPresentationCard(card) {
        const item = {
            cardId: String(card.card_id || ""),
            kind: String(card.kind || "info"),
            title: String(card.title || ""),
            subtitle: String(card.subtitle || ""),
            cardValue: String(card.value || ""),
            detail: String(card.detail || "")
        }
        const existing = cardIndexById(item.cardId)
        if (existing >= 0) {
            presentationCards.set(existing, item)
            return
        }
        if (presentationCards.count >= 6)
            presentationCards.remove(0)
        presentationCards.append(item)

    }

    function historyShouldFollow() {
        const threshold = 64 * scale
        return history.atYEnd
            || history.contentHeight <= history.height
            || history.contentY + history.height >= history.contentHeight - threshold
    }

    ListModel { id: messages }
    ListModel { id: presentationCards }

    Connections {
        target: agent

        function onMessage(role, text) {
            if (role === "user") {
                window.toolEvents = []
                window.currentToolEvents = []
                window.inspectorPinned = false
                window.inspectedMetadata = ({})
            }
            messages.append({speaker: role, body: text, responseMetaJson: "{}", responseToolsJson: "[]"})
            Qt.callLater(function() { history.positionViewAtEnd() })
        }

        function onDelta(text) {
            if (!messages.count)
                return
            const follow = window.historyShouldFollow()
            const index = messages.count - 1
            messages.setProperty(index, "body", messages.get(index).body + text)
            if (follow)
                Qt.callLater(function() { history.positionViewAtEnd() })
        }

        function onResponseMetaEvent(event) {
            // Convert QVariant containers to JS arrays for the details view.
            event = JSON.parse(JSON.stringify(event))
            if (!window.inspectorPinned) window.inspectedMetadata = event
            for (let i = messages.count - 1; i >= 0; --i) {
                if (messages.get(i).speaker === "assistant") {
                    messages.setProperty(i, "responseMetaJson", JSON.stringify(event))
                    break
                }
            }
        }

        function onToolEvent(event) {
            window.currentToolEvents = window.currentToolEvents.concat([event]).slice(-32)
            if (!window.inspectorPinned) window.toolEvents = window.currentToolEvents
            for (let i = messages.count - 1; i >= 0; --i) {
                if (messages.get(i).speaker === "assistant") {
                    messages.setProperty(i, "responseToolsJson", JSON.stringify(window.currentToolEvents))
                    break
                }
            }
            if (event.type === "tool.completed" || event.type === "tool_result")
                return
            const text = event.display_text
            window.pendingToolDisplay = typeof text === "string" && text.length
                ? text
                : qsTr("Meo AI needs your confirmation before continuing.")
        }

        function onPresentationEvent(event) {
            const card = event.card
            if (!card || !card.title)
                return
            window.upsertPresentationCard(card)
        }

        function onResetChat() {
            messages.clear()
            presentationCards.clear()
            window.pendingToolDisplay = ""
            window.inspectedMetadata = ({})
            window.inspectorPinned = false
            window.toolEvents = []
            window.currentToolEvents = []
        }
    }

    Shortcut {
        sequence: "Ctrl+N"
        enabled: !agent.busy && !agent.actionBusy && !agent.options.length
        onActivated: agent.newChat()
    }

    TextEdit {
        id: clipboardText
        visible: false
        function copyText(value) { text = value; selectAll(); copy(); deselect() }
    }

    SplitView {
        id: workspaceLayout
        objectName: "meoAiLayout"
        anchors.fill: parent
        anchors.margins: window.compact ? 8 * window.scale : 12 * window.scale
        orientation: Qt.Horizontal
        onResizingChanged: {
            if (!resizing) {
                if (window.showSidebar && sidebar.visible) layoutPreferences.sidebarWidth = sidebar.width / window.scale
                if (window.showDock) layoutPreferences.detailsWidth = inspectorDock.width / window.scale
            }
        }
        handle: Rectangle {
            id: splitterHandle
            objectName: "meoAiResizeHandle"
            implicitWidth: 12 * window.scale
            color: "transparent"
            Rectangle {
                anchors.centerIn: parent
                width: 3 * window.scale
                height: Math.min(parent.height * 0.3, 72 * window.scale)
                radius: width / 2
                color: splitterHandle.SplitHandle.pressed ? MeoTheme.primary : MeoTheme.outlineVariant
                opacity: splitterHandle.SplitHandle.hovered || splitterHandle.SplitHandle.pressed ? 1 : 0.5
            }
        }

        Rectangle {
            id: sidebar
            objectName: "meoAiSidebar"
            visible: !window.compact && !window.sidebarHidden
            SplitView.preferredWidth: window.showSidebar ? layoutPreferences.sidebarWidth * window.scale : 72 * window.scale
            SplitView.minimumWidth: (window.showSidebar ? 200 : 72) * window.scale
            SplitView.maximumWidth: (window.showSidebar ? 360 : 72) * window.scale
            radius: 26 * window.scale
            color: MeoTheme.surfaceContainerLow

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14 * window.scale
                spacing: 8 * window.scale
                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 8 * window.scale
                    Layout.bottomMargin: 18 * window.scale
                    spacing: 12 * window.scale
                    AiLogo { Layout.preferredWidth: 40 * window.scale; Layout.preferredHeight: 40 * window.scale }
                    ColumnLayout {
                        visible: window.showSidebar
                        Layout.fillWidth: true
                        spacing: 2 * window.scale
                        MeoText { text: qsTr("Meo AI"); typeRole: "title"; typeSize: "medium"; color: MeoTheme.contentOnSurface }
                        MeoText { Layout.fillWidth: true; text: qsTr("A little help. More possibility."); elide: Text.ElideRight; typeRole: "label"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant }
                    }
                }
                NavigationButton {
                    objectName: "meoAiNewChat"
                    Layout.fillWidth: true
                    text: window.showSidebar ? qsTr("New chat") : ""
                    icon.name: "add"
                    type: "filled"; size: "s"
                    Accessible.name: qsTr("New chat")
                    enabled: !agent.busy && !agent.actionBusy && !agent.options.length
                    onClicked: agent.newChat()
                    ToolTip.visible: hovered && !window.showSidebar
                    ToolTip.text: Accessible.name
                }
                MeoTextField {
                    id: chatSearch
                    visible: window.showSidebar && messages.count > 0
                    Layout.fillWidth: true
                    placeholder: qsTr("Find in this conversation")
                    leadingIcon: "search"
                    size: "s"
                    showClearButton: true
                    Accessible.name: qsTr("Find in this conversation")
                }
                Repeater {
                    model: [
                        {label: qsTr("Chat"), icon: "chat_bubble", action: "chat"},
                        {label: qsTr("Models by job"), icon: "deployed_code", action: "models"},
                        {label: qsTr("Memory"), icon: "neurology", action: "memory"},
                        {label: qsTr("Resources"), icon: "folder_open", action: "resources"}
                    ]
                    delegate: NavigationButton {
                        required property var modelData
                        Layout.fillWidth: true
                        text: window.showSidebar ? modelData.label : ""
                        icon.name: modelData.icon
                        type: modelData.action === "chat" ? "tonal" : "text"
                        size: "s"
                        Accessible.name: modelData.label
                        ToolTip.visible: hovered && !window.showSidebar
                        ToolTip.text: modelData.label
                        onClicked: {
                            if (modelData.action === "models") modelRolesPopup.open()
                            else if (modelData.action === "memory") { agent.refreshMemory(); window.openInspector(1) }
                            else if (modelData.action === "resources") window.openInspector(2)
                            else { inspectorOpen = false; history.positionViewAtEnd(); composer.forceActiveFocus() }
                        }
                    }
                }
                MeoText {
                    visible: window.showSidebar
                    Layout.topMargin: 22 * window.scale
                    Layout.leftMargin: 12 * window.scale
                    text: qsTr("This conversation")
                    typeRole: "label"; typeSize: "small"
                    color: MeoTheme.contentOnSurfaceVariant
                }
                NavigationButton {
                    visible: window.showSidebar
                    Layout.fillWidth: true
                    text: messages.count ? qsTr("Current chat") : qsTr("A fresh start")
                    icon.name: "chat"
                    type: "tonal"; size: "s"
                    onClicked: { history.positionViewAtEnd(); composer.forceActiveFocus() }
                }
                MeoText {
                    visible: window.showSidebar && chatSearch.text.length > 0
                    Layout.fillWidth: true
                    Layout.margins: 8 * window.scale
                    text: qsTr("%1 matching messages").arg(window.matchingMessages(chatSearch.text))
                    typeRole: "label"; typeSize: "small"
                    color: MeoTheme.contentOnSurfaceVariant
                }
                Item { Layout.fillHeight: true }
                NavigationButton {
                    Layout.fillWidth: true
                    text: window.showSidebar ? qsTr("AI settings") : ""
                    icon.name: "tune"; type: "text"; size: "s"
                    Accessible.name: qsTr("AI settings")
                    onClicked: window.openInspector(3)
                }
                Rectangle {
                    visible: window.showSidebar
                    Layout.fillWidth: true
                    implicitHeight: 76 * window.scale
                    radius: 20 * window.scale
                    color: MeoTheme.surfaceContainer
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 12 * window.scale
                        spacing: 12 * window.scale
                        MeoIcon { icon: "computer"; size: 28; color: MeoTheme.primary }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4 * window.scale
                            MeoText { text: qsTr("This computer"); typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurface }
                            MeoText {
                                text: agent.agentState.ready ? qsTr("Service connected") : qsTr("Service not connected")
                                typeRole: "label"; typeSize: "small"
                                color: MeoTheme.contentOnSurfaceVariant
                            }
                        }
                        Rectangle {
                            width: 7 * window.scale; height: width; radius: width / 2
                            color: agent.agentState.ready ? MeoTheme.primary : MeoTheme.outline
                        }
                    }
                }
            }
        }

        Rectangle {
            id: mainPane
            SplitView.fillWidth: true
            SplitView.minimumWidth: 320 * window.scale
            radius: 26 * window.scale
            color: MeoTheme.surfaceContainerLowest
            clip: true

            RowLayout {
                id: compactHeader
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                anchors.leftMargin: window.pageMargin; anchors.rightMargin: window.pageMargin
                height: 76 * window.scale
                spacing: 10 * window.scale
                MeoIconButton {
                    objectName: "meoAiToggleSidebar"
                    visible: !window.compact
                    icon.name: "menu"; type: "standard"; size: "xs"
                    Accessible.name: window.sidebarHidden ? qsTr("Show navigation") : qsTr("Hide navigation")
                    ToolTip.visible: hovered; ToolTip.text: Accessible.name
                    onClicked: window.sidebarHidden = !window.sidebarHidden
                }
                AiLogo {
                    visible: window.compact
                    Layout.preferredWidth: 32 * window.scale; Layout.preferredHeight: 32 * window.scale
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3 * window.scale
                    MeoText {
                        Layout.fillWidth: true
                        text: messages.count ? window.conversationTitle : qsTr("Your space to think")
                        typeRole: "title"; typeSize: "small"
                        color: MeoTheme.contentOnSurface
                        elide: Text.ElideRight
                    }
                    MeoText {
                        Layout.fillWidth: true
                        text: window.previewMode ? qsTr("Design preview · sample content") : agent.status
                        typeRole: "label"; typeSize: "small"
                        color: MeoTheme.contentOnSurfaceVariant
                        elide: Text.ElideRight
                        ToolTip.visible: subtitleHover.hovered
                        ToolTip.text: text
                        HoverHandler { id: subtitleHover }
                    }
                }
                MeoIconButton {
                    visible: window.compact
                    icon.name: "add"; type: "standard"; size: "xs"
                    Accessible.name: qsTr("New chat")
                    enabled: !agent.busy && !agent.actionBusy && !agent.options.length
                    onClicked: agent.newChat()
                }
                MeoIconButton {
                    icon.name: "right_panel_open"; type: window.inspectorOpen ? "tonal" : "standard"; size: "xs"
                    Accessible.name: qsTr("Response details and settings")
                    ToolTip.visible: hovered; ToolTip.text: Accessible.name
                    onClicked: {
                        if (window.showDock) window.inspectorOpen = false
                        else window.openInspector(window.inspectorTab)
                    }
                }
            }

            ListView {
                id: history
                objectName: "meoAiHistory"
                anchors.top: compactHeader.bottom
                anchors.topMargin: 16 * window.scale
                anchors.bottom: confirmationSurface.visible ? confirmationSurface.top : composerShell.top
                anchors.bottomMargin: 16 * window.scale
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(parent.width - 2 * window.pageMargin, window.contentMaxWidth)
                clip: true
                spacing: 24 * window.scale
                model: messages
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                delegate: Item {
                    id: messageDelegate
                    required property string speaker
                    required property int index
                    required property string body
                    required property string responseMetaJson
                    readonly property var responseMeta: JSON.parse(responseMetaJson)
                    required property string responseToolsJson
                    readonly property bool fromUser: speaker === "user"
                    readonly property bool hasResponseMeta: !fromUser && !!responseMeta && Object.keys(responseMeta).length > 0
                    readonly property bool matches: !chatSearch.text.length || body.toLowerCase().indexOf(chatSearch.text.toLowerCase()) >= 0
                    width: history.width
                    implicitHeight: matches ? messageBody.implicitHeight : 0
                    visible: matches

                    AiLogo {
                        visible: !messageDelegate.fromUser && !window.compact
                        width: 32 * window.scale; height: width
                        anchors.left: parent.left; anchors.top: parent.top
                    }
                    ColumnLayout {
                        id: messageBody
                        width: messageDelegate.fromUser ? Math.min(messageDelegate.width * 0.86, 600 * window.scale)
                               : messageDelegate.width - (window.compact ? 0 : 48 * window.scale)
                        anchors.right: parent.right
                        spacing: 8 * window.scale
                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: messageText.implicitHeight + (messageDelegate.fromUser ? 28 : 12) * window.scale
                            radius: 22 * window.scale
                            color: messageDelegate.fromUser ? MeoTheme.secondaryContainer : "transparent"
                            MeoText {
                                id: messageText
                                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                                anchors.margins: (messageDelegate.fromUser ? 14 : 6) * window.scale
                                text: messageDelegate.body
                                textFormat: messageDelegate.fromUser ? Text.PlainText : Text.MarkdownText
                                wrapMode: Text.Wrap
                                typeRole: "body"; typeSize: "medium"
                                fontScaleOverride: 1.06
                                color: MeoTheme.contentOnSurface
                                linkColor: MeoTheme.primary
                                onLinkActivated: function(link) {
                                    if (/^https?:\/\//i.test(link)) Qt.openUrlExternally(link)
                                }
                            }
                        }
                        RowLayout {
                            visible: !messageDelegate.fromUser && messageDelegate.body.length > 0
                            Layout.fillWidth: true
                            spacing: 2 * window.scale
                            MeoIconButton {
                                icon.name: "content_copy"; type: "standard"; size: "xs"
                                Accessible.name: qsTr("Copy response")
                                ToolTip.visible: hovered; ToolTip.text: Accessible.name
                                onClicked: clipboardText.copyText(messageDelegate.body)
                            }
                            MeoButton {
                                objectName: messageDelegate.fromUser ? "" : "meoAiResponseDetails-" + messageDelegate.index
                                text: messageDelegate.hasResponseMeta ? window.responseMetaSummary(messageDelegate.responseMeta) : qsTr("Response details")
                                type: "text"; size: "xs"
                                onClicked: {
                                    window.inspectedMetadata = messageDelegate.responseMeta || ({})
                                    window.toolEvents = JSON.parse(messageDelegate.responseToolsJson)
                                    window.inspectorPinned = true
                                    window.openInspector(0)
                                }
                            }
                            Item { Layout.fillWidth: true }
                        }
                    }
                }
                footer: Item {
                    width: history.width
                    height: presentationCards.count > 0 && !chatSearch.text.length ? cardsGrid.implicitHeight + 24 * window.scale : 0
                    visible: height > 0
                    GridLayout {
                        id: cardsGrid
                        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                        anchors.topMargin: 12 * window.scale
                        columns: width >= 680 * window.scale ? 3 : width >= 440 * window.scale ? 2 : 1
                        columnSpacing: 10 * window.scale; rowSpacing: 10 * window.scale
                        Repeater {
                            model: presentationCards
                            delegate: PresentationCard {
                                objectName: "meoAiPresentationCard"
                                required kind
                                required title
                                required subtitle
                                required cardValue
                                required detail
                                Layout.fillWidth: true
                                Layout.preferredWidth: (cardsGrid.width - (cardsGrid.columns - 1) * cardsGrid.columnSpacing) / cardsGrid.columns
                                Layout.fillHeight: true
                            }
                        }
                    }
                }
            }

            ColumnLayout {
                id: emptyIntro
                visible: messages.count === 0
                width: Math.min(parent.width - 2 * window.pageMargin, 700 * window.scale)
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: composerShell.top
                anchors.bottomMargin: 32 * window.scale
                spacing: 16 * window.scale
                AiLogo { Layout.alignment: Qt.AlignHCenter; Layout.preferredWidth: 56 * window.scale; Layout.preferredHeight: 56 * window.scale }
                MeoText {
                    Layout.fillWidth: true
                    text: qsTr("What shall we work on?")
                    typeRole: "title"; typeSize: "big"
                    color: MeoTheme.contentOnSurface
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                }
                MeoText {
                    Layout.fillWidth: true
                    text: qsTr("A question, an idea, a project. Start anywhere.")
                    typeRole: "body"; typeSize: "medium"
                    color: MeoTheme.contentOnSurfaceVariant
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                }
            }

            Rectangle {
                id: confirmationSurface
                objectName: "meoAiConfirmation"
                visible: agent.options.length > 0 && window.pendingToolDisplay.length > 0
                width: composerShell.width
                implicitHeight: confirmationColumn.implicitHeight + 28 * window.scale
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: composerShell.top
                anchors.bottomMargin: 12 * window.scale
                radius: 22 * window.scale
                color: MeoTheme.secondaryContainer
                border.width: 1; border.color: MeoTheme.outlineVariant
                ColumnLayout {
                    id: confirmationColumn
                    anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                    anchors.margins: 14 * window.scale
                    spacing: 10 * window.scale
                    MeoText { text: qsTr("Your confirmation is needed"); typeRole: "label"; color: MeoTheme.contentOnSurface }
                    MeoText {
                        Layout.fillWidth: true
                        text: window.pendingToolDisplay; textFormat: Text.PlainText
                        wrapMode: Text.Wrap; color: MeoTheme.contentOnSurfaceVariant
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Repeater {
                            model: agent.options
                            delegate: MeoButton {
                                required property var modelData
                                required property int index
                                Layout.fillWidth: true
                                text: modelData.title; type: index === 0 ? "outlined" : "filled"; size: "s"
                                enabled: !agent.actionBusy && (agent.serviceMode || !agent.busy)
                                onClicked: agent.choose(index)
                            }
                        }
                    }
                }
            }

            Rectangle {
                id: composerShell
                objectName: "meoAiComposerShell"
                width: Math.min(parent.width - 2 * window.pageMargin, window.composerMaxWidth)
                implicitHeight: composerColumn.implicitHeight + 24 * window.scale
                anchors.horizontalCenter: parent.horizontalCenter
                y: messages.count === 0
                    ? Math.round(Math.min(parent.height - height - 98 * window.scale, parent.height * 0.51))
                    : Math.round(parent.height - height - 34 * window.scale)
                radius: 26 * window.scale
                color: MeoTheme.surfaceContainerLow
                border.width: 1
                border.color: composer.activeFocus ? MeoTheme.primary : MeoTheme.outlineVariant
                ColumnLayout {
                    id: composerColumn
                    anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                    anchors.margins: 12 * window.scale
                    spacing: 8 * window.scale
                    TextArea {
                        id: composer
                        objectName: "meoAiComposer"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 60 * window.scale
                        enabled: !agent.busy && !agent.actionBusy && !agent.options.length
                        placeholderText: qsTr("Ask anything, or hand off a task…")
                        wrapMode: TextEdit.Wrap
                        selectByMouse: true
                        padding: 6 * window.scale
                        color: MeoTheme.contentOnSurface
                        font.family: MeoTheme.typefacePlain
                        font.pixelSize: MeoTheme.bodyLarge.size * MeoTheme.fontScale * window.scale
                        background: null
                        Keys.onPressed: function(event) {
                            const enter = event.key === Qt.Key_Return || event.key === Qt.Key_Enter
                            if (enter && !(event.modifiers & Qt.ShiftModifier) && !inputMethodComposing) {
                                window.submit(text)
                                event.accepted = true
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6 * window.scale
                        MeoIconButton {
                            icon.name: "attach_file"; type: "standard"; size: "xs"
                            Accessible.name: qsTr("Attach long text")
                            ToolTip.visible: hovered; ToolTip.text: Accessible.name
                            enabled: agent.serviceMode && !agent.busy && !agent.actionBusy
                            onClicked: longPastePanel.open()
                        }
                        MeoButton {
                            visible: agent.serviceMode
                            text: window.selectedModelLabel.length && !window.compact ? window.selectedModelLabel : qsTr("Models")
                            icon.name: "auto_awesome"
                            type: "tonal"; size: "xs"
                            enabled: !agent.actionBusy && !agent.metadataBusy
                            onClicked: modelRolesPopup.open()
                        }
                        MeoButton {
                            visible: agent.pendingResources.length > 0
                            text: qsTr("%1 attached").arg(agent.pendingResources.length)
                            type: "text"; size: "xs"
                            onClicked: window.openInspector(2)
                        }
                        Item { Layout.fillWidth: true }
                        MeoText {
                            visible: !window.compact
                            text: agent.busy ? qsTr("Working…") : qsTr("Shift + Enter for a new line")
                            typeRole: "label"; typeSize: "small"
                            color: MeoTheme.contentOnSurfaceVariant
                        }
                        MeoIconButton {
                            objectName: "meoAiSend"
                            icon.name: agent.busy && agent.serviceMode ? "stop" : "arrow_upward"
                            type: "filled"; size: "s"
                            Accessible.name: agent.busy && agent.serviceMode ? qsTr("Stop") : qsTr("Send message")
                            ToolTip.visible: hovered; ToolTip.text: Accessible.name
                            enabled: agent.busy && agent.serviceMode ? !agent.actionBusy
                                : (!agent.busy && !agent.actionBusy && !agent.options.length && composer.text.trim().length > 0)
                            onClicked: {
                                if (agent.busy && agent.serviceMode) agent.cancel()
                                else window.submit(composer.text)
                            }
                        }
                    }
                }
            }
            RowLayout {
                id: quickActions
                visible: messages.count === 0 && !agent.busy && !agent.options.length
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: composerShell.bottom
                anchors.topMargin: 16 * window.scale
                spacing: 8 * window.scale
                Repeater {
                    model: [{label: qsTr("Code"), icon: "code", prompt: qsTr("Help me work on my current coding project.")},
                            {label: qsTr("Write"), icon: "edit_note", prompt: qsTr("Help me write something. Ask what I want to create.")},
                            {label: qsTr("Plan"), icon: "checklist", prompt: qsTr("Help me plan this task before we start.")},
                            {label: qsTr("Explore"), icon: "travel_explore", prompt: qsTr("Help me explore an idea. Ask what I am curious about.")}]
                    delegate: MeoButton {
                        required property var modelData
                        text: modelData.label; icon.name: modelData.icon
                        type: "outlined"; size: "xs"
                        onClicked: { composer.text = modelData.prompt; composer.forceActiveFocus() }
                    }
                }
            }
            MeoText {
                visible: messages.count > 0
                anchors.horizontalCenter: composerShell.horizontalCenter
                anchors.top: composerShell.bottom
                anchors.topMargin: 7 * window.scale
                text: qsTr("AI can make mistakes. Review important actions.")
                typeRole: "label"; typeSize: "small"
                color: MeoTheme.contentOnSurfaceVariant
            }
        }
        Loader {
            id: inspectorDock
            visible: window.showDock
            active: visible
            SplitView.preferredWidth: layoutPreferences.detailsWidth * window.scale
            SplitView.minimumWidth: 300 * window.scale
            SplitView.maximumWidth: 520 * window.scale
            sourceComponent: detailsComponent
        }
    }

    Component {
        id: detailsComponent
        DetailsPane {
            metadata: window.inspectedMetadata
            toolEvents: window.toolEvents.filter(function(event) {
                return !window.inspectedMetadata.request_id || event.request_id === window.inspectedMetadata.request_id
            })
            memoryState: agent.memoryState
            memories: agent.memories
            resources: agent.pendingResources
            skills: agent.skills
            ready: !!agent.agentState.ready
            busy: agent.busy || agent.actionBusy
            tab: window.inspectorTab
            onSelectedTabRequested: function(selectedTab) { window.inspectorTab = selectedTab }
            onCloseRequested: { window.inspectorOpen = false; inspectorOverlay.close() }
            onManageMemoryRequested: memoryPanel.open()
            onAttachRequested: longPastePanel.open()
            onDiscardRequested: function(id) { agent.discardPendingResource(id) }
            onModelsRequested: modelRolesPopup.open()
            onControlsRequested: aiControlsPopup.open()
        }
    }
    Popup {
        id: inspectorOverlay
        objectName: "meoAiInspectorOverlay"
        parent: Overlay.overlay
        modal: true
        focus: true
        width: Math.min(440 * window.scale, window.width - 28 * window.scale)
        height: Math.min(780 * window.scale, window.height - 28 * window.scale)
        x: parent ? parent.width - width - 14 * window.scale : 0
        y: parent ? Math.round((parent.height - height) / 2) : 0
        padding: 0
        background: null
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        contentItem: Loader { active: inspectorOverlay.visible; sourceComponent: detailsComponent }
        onClosed: if (!window.showDock) window.inspectorOpen = false
    }
    MemoryPanel {
        id: memoryPanel
        parent: Overlay.overlay
        x: (window.width - width) / 2; y: (window.height - height) / 2
        memoryState: agent.memoryState; memories: agent.memories
        busy: agent.actionBusy
        onRefreshRequested: function(query) { agent.refreshMemory(query) }
        onEnabledChangeRequested: function(enabled) { agent.setMemoryEnabled(enabled) }
        onCreateRequested: function(text, pinned) { agent.createMemory(text, pinned) }
        onUpdateRequested: function(id, text, pinned) { agent.updateMemory(id, text, pinned) }
        onDeleteRequested: function(id) { agent.deleteMemory(id) }
    }
    LongPastePanel {
        id: longPastePanel
        parent: Overlay.overlay
        x: (window.width - width) / 2; y: (window.height - height) / 2
        onAttachRequested: function(name, text) { agent.addLongTextResource(name, text) }
    }
    AiControlsPopup {
        id: aiControlsPopup
        parent: Overlay.overlay
        controls: agent.controls
        x: parent ? (parent.width - width) / 2 : 0
        y: parent ? (parent.height - height) / 2 : 0
        onChangeRequested: function(id, value) { agent.setControl(id, value) }
    }
    Popup {
        id: modelRolesPopup
        objectName: "meoAiModelRolesPopup"
        modal: true
        focus: true
        x: Math.round((window.width - width) / 2)
        y: Math.round((window.height - height) / 2)
        width: Math.min(620 * window.scale, window.width - 28 * window.scale)
        height: Math.min(650 * window.scale, window.height - 28 * window.scale)
        padding: 0
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            radius: 24 * window.scale
            color: MeoTheme.surface
            border.width: Math.max(1, window.scale)
            border.color: MeoTheme.outlineVariant
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20 * window.scale
            spacing: 12 * window.scale

            RowLayout {
                Layout.fillWidth: true
                spacing: 8 * window.scale

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3 * window.scale

                    MeoText {
                        Layout.fillWidth: true
                        text: qsTr("Models by job")
                        typeRole: "title"
                        typeSize: "medium"
                        color: MeoTheme.contentOnSurface
                    }

                    MeoText {
                        Layout.fillWidth: true
                        text: qsTr("Choose where Meo AI spends model quality.")
                        typeRole: "body"
                        typeSize: "small"
                        color: MeoTheme.contentOnSurfaceVariant
                        wrapMode: Text.Wrap
                    }
                }

                MeoButton {
                    text: qsTr("Close")
                    type: "text"
                    size: "xs"
                    onClicked: modelRolesPopup.close()
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(1, window.scale)
                color: MeoTheme.outlineVariant
                opacity: 0.38
            }

            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true

                Column {
                    width: parent.width
                    spacing: 8 * window.scale

                    Repeater {
                        model: agent.modelRoles

                        delegate: Rectangle {
                            required property var modelData
                            width: parent.width
                            implicitHeight: roleColumn.implicitHeight + 24 * window.scale
                            radius: 18 * window.scale
                            color: MeoTheme.surfaceContainerLow

                            ColumnLayout {
                                id: roleColumn
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 12 * window.scale
                                spacing: 7 * window.scale

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8 * window.scale

                                    MeoText {
                                        Layout.fillWidth: true
                                        text: String(modelData.label || modelData.role_id || "")
                                        typeRole: "label"
                                        typeSize: "medium"
                                        color: MeoTheme.contentOnSurface
                                        elide: Text.ElideRight
                                    }

                                    MeoText {
                                        text: modelData.workload === "auxiliary"
                                            ? qsTr("Background")
                                            : qsTr("Primary")
                                        typeRole: "label"
                                        typeSize: "small"
                                        color: MeoTheme.contentOnSurfaceVariant
                                        opacity: 0.66
                                    }
                                }

                                MeoText {
                                    Layout.fillWidth: true
                                    text: String(modelData.description || "")
                                    typeRole: "body"
                                    typeSize: "small"
                                    color: MeoTheme.contentOnSurfaceVariant
                                    wrapMode: Text.Wrap
                                }

                                MeoExposedDropdown {
                                    Layout.fillWidth: true
                                    label: qsTr("Model")
                                    model: agent.models
                                    textRole: "label"
                                    valueRole: "model_id"
                                    type: "outlined"
                                    enabled: agent.models.length > 0 && !agent.actionBusy
                                    currentValue: String(modelData.preferred_model_id
                                        || modelData.fallback_model_id
                                        || "")

                                    onSelected: function(index, value) {
                                        if (index < 0 || index >= agent.models.length || !String(value).length)
                                            return
                                        agent.setModelRole(
                                            String(modelData.role_id || ""),
                                            String(value))
                                    }
                                }

                                MeoText {
                                    Layout.fillWidth: true
                                    text: modelData.runtime_supported
                                        ? qsTr("Independent routing is active.")
                                        : qsTr("Saved now; independent routing is not active yet.")
                                    typeRole: "label"
                                    typeSize: "small"
                                    color: MeoTheme.contentOnSurfaceVariant
                                    opacity: 0.68
                                    wrapMode: Text.Wrap
                                }
                            }
                        }
                    }
                }
            }

            MeoText {
                Layout.fillWidth: true
                text: qsTr("Judge can classify and rank, but privileged actions still require Router policy and explicit confirmation.")
                typeRole: "label"
                typeSize: "small"
                color: MeoTheme.contentOnSurfaceVariant
                opacity: 0.72
                wrapMode: Text.Wrap
            }
        }
    }
}

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0

ApplicationWindow {
    id: window
    width: 1180
    height: 780
    minimumWidth: 640
    minimumHeight: 520
    visible: true
    title: qsTr("Meo AI")
    color: MeoTheme.surface

    readonly property real scale: MeoTheme.globalScale
    readonly property bool compact: width < 820 * scale
    readonly property bool wideSidebar: width >= 1120 * scale
    readonly property real pageMargin: Math.max(16 * scale, Math.min(34 * scale, width * 0.026))
    readonly property real contentMaxWidth: 900 * scale
    readonly property string selectedModelLabel: {
        for (let i = 0; i < agent.models.length; ++i) {
            const model = agent.models[i]
            if (model.selected === true)
                return String(model.label || model.model_id || "")
        }
        return ""
    }

    property string pendingToolDisplay: ""

    Component.onCompleted: {
        if (agent.serviceMode)
            agent.refreshServiceMetadata()
    }

    function submit(text) {
        const value = String(text).trim()
        if (!value.length || agent.busy || agent.actionBusy || agent.options.length)
            return
        agent.send(value)
        composer.text = ""
    }

    function modelIndex(modelId) {
        const wanted = String(modelId || "")
        for (let i = 0; i < agent.models.length; ++i) {
            if (String(agent.models[i].model_id || "") === wanted)
                return i
        }
        return agent.models.length ? 0 : -1
    }

    function cardKindLabel(kind) {
        switch (String(kind || "")) {
        case "status": return qsTr("STATUS")
        case "metric": return qsTr("METRIC")
        case "file": return qsTr("FILE")
        case "system": return qsTr("SYSTEM")
        default: return qsTr("INFO")
        }
    }

    ListModel { id: messages }
    ListModel { id: presentationCards }

    Connections {
        target: agent

        function onMessage(role, text) {
            messages.append({speaker: role, body: text})
            history.positionViewAtEnd()
        }

        function onDelta(text) {
            if (!messages.count)
                return
            const index = messages.count - 1
            messages.setProperty(index, "body", messages.get(index).body + text)
            history.positionViewAtEnd()
        }

        function onToolEvent(event) {
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
            if (presentationCards.count >= 6)
                presentationCards.remove(0)
            presentationCards.append({
                cardId: String(card.card_id || ""),
                kind: String(card.kind || "info"),
                title: String(card.title || ""),
                subtitle: String(card.subtitle || ""),
                cardValue: String(card.value || ""),
                detail: String(card.detail || "")
            })
        }

        function onResetChat() {
            messages.clear()
            presentationCards.clear()
            window.pendingToolDisplay = ""
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            id: sidebar
            visible: !window.compact
            Layout.fillHeight: true
            Layout.preferredWidth: window.wideSidebar ? 236 * window.scale : 78 * window.scale
            color: MeoTheme.surfaceContainerLow

            Rectangle {
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                width: Math.max(1, window.scale)
                color: MeoTheme.outlineVariant
                opacity: 0.45
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14 * window.scale
                spacing: 14 * window.scale

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10 * window.scale

                    MeoAiMark {
                        Layout.preferredWidth: 38 * window.scale
                        Layout.preferredHeight: 38 * window.scale
                    }

                    ColumnLayout {
                        visible: window.wideSidebar
                        Layout.fillWidth: true
                        spacing: -1 * window.scale

                        Text {
                            text: qsTr("Meo AI")
                            color: MeoTheme.contentOnSurface
                            font.pixelSize: MeoTheme.titleMedium.size * window.scale
                            font.weight: Font.DemiBold
                        }

                        Text {
                            text: qsTr("Modern · Expressive · Open")
                            color: MeoTheme.contentOnSurfaceVariant
                            font.pixelSize: MeoTheme.labelSmall.size * window.scale
                            font.weight: MeoTheme.labelSmall.weight
                            opacity: 0.82
                        }
                    }
                }

                MeoButton {
                    Layout.fillWidth: true
                    text: window.wideSidebar ? qsTr("New chat") : "+"
                    type: "filled"
                    enabled: !agent.busy && !agent.actionBusy && !agent.options.length
                    onClicked: agent.newChat()
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 7 * window.scale

                    Text {
                        visible: window.wideSidebar
                        text: qsTr("Workspace")
                        color: MeoTheme.contentOnSurfaceVariant
                        font.pixelSize: MeoTheme.labelSmall.size * window.scale
                        font.weight: Font.DemiBold
                        leftPadding: 2 * window.scale
                    }

                    MeoCard {
                        Layout.fillWidth: true
                        type: "filled"
                        compact: true
                        selected: true

                        contentItem: RowLayout {
                            spacing: 9 * window.scale

                            Rectangle {
                                Layout.preferredWidth: 8 * window.scale
                                Layout.preferredHeight: 8 * window.scale
                                radius: width / 2
                                color: MeoTheme.primary
                            }

                            ColumnLayout {
                                visible: window.wideSidebar
                                Layout.fillWidth: true
                                spacing: 0

                                Text {
                                    Layout.fillWidth: true
                                    text: qsTr("Current chat")
                                    color: MeoTheme.contentOnSurface
                                    font.pixelSize: MeoTheme.labelLarge.size * window.scale
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: agent.busy ? qsTr("Working") : qsTr("Ready")
                                    color: MeoTheme.contentOnSurfaceVariant
                                    font.pixelSize: MeoTheme.labelSmall.size * window.scale
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 7 * window.scale

                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 38 * window.scale
                        radius: 14 * window.scale
                        color: MeoTheme.surface

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 12 * window.scale
                            anchors.rightMargin: 12 * window.scale
                            spacing: 8 * window.scale

                            Rectangle {
                                Layout.preferredWidth: 7 * window.scale
                                Layout.preferredHeight: 7 * window.scale
                                radius: width / 2
                                color: agent.serviceMode
                                    ? MeoTheme.primary
                                    : MeoTheme.contentOnSurfaceVariant
                            }

                            Text {
                                visible: window.wideSidebar
                                Layout.fillWidth: true
                                text: agent.serviceMode ? qsTr("Local service") : qsTr("Compatibility")
                                color: MeoTheme.contentOnSurfaceVariant
                                font.pixelSize: MeoTheme.labelSmall.size * window.scale
                                elide: Text.ElideRight
                            }
                        }
                    }

                    Text {
                        visible: window.wideSidebar
                        Layout.fillWidth: true
                        text: qsTr("Local-first · permissions stay outside the model")
                        color: MeoTheme.contentOnSurfaceVariant
                        font.pixelSize: MeoTheme.labelSmall.size * window.scale
                        wrapMode: Text.Wrap
                        opacity: 0.68
                    }
                }
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                Rectangle {
                    id: topBar
                    Layout.fillWidth: true
                    Layout.preferredHeight: 66 * window.scale
                    color: MeoTheme.surface

                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: Math.max(1, window.scale)
                        color: MeoTheme.outlineVariant
                        opacity: 0.34
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: window.pageMargin
                        anchors.rightMargin: window.pageMargin
                        spacing: 10 * window.scale

                        MeoAiMark {
                            visible: window.compact
                            Layout.preferredWidth: 32 * window.scale
                            Layout.preferredHeight: 32 * window.scale
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0

                            Text {
                                text: qsTr("Meo AI")
                                color: MeoTheme.contentOnSurface
                                font.pixelSize: MeoTheme.titleMedium.size * window.scale
                                font.weight: Font.DemiBold
                            }

                            Text {
                                Layout.fillWidth: true
                                text: agent.status
                                color: MeoTheme.contentOnSurfaceVariant
                                font.pixelSize: MeoTheme.labelSmall.size * window.scale
                                elide: Text.ElideRight
                            }
                        }

                        Rectangle {
                            visible: !window.compact
                            implicitWidth: modelLabel.implicitWidth + 24 * window.scale
                            implicitHeight: 32 * window.scale
                            radius: 12 * window.scale
                            color: MeoTheme.surfaceContainerLow
                            border.width: Math.max(1, window.scale)
                            border.color: MeoTheme.outlineVariant

                            Text {
                                id: modelLabel
                                anchors.centerIn: parent
                                text: agent.serviceMode
                                    ? (window.selectedModelLabel.length
                                        ? window.selectedModelLabel
                                        : qsTr("Local service"))
                                    : qsTr("Legacy API")
                                color: MeoTheme.contentOnSurfaceVariant
                                font.pixelSize: MeoTheme.labelSmall.size * window.scale
                                font.weight: Font.DemiBold
                            }
                        }

                        MeoButton {
                            visible: agent.serviceMode
                            text: window.compact ? qsTr("Roles") : qsTr("Model roles")
                            type: "tonal"
                            enabled: !agent.actionBusy && !agent.metadataBusy
                            onClicked: modelRolesPopup.open()
                        }

                        MeoButton {
                            visible: agent.serviceMode && agent.busy
                            text: qsTr("Stop")
                            type: "tonal"
                            enabled: !agent.actionBusy
                            onClicked: agent.cancel()
                        }

                        MeoButton {
                            visible: window.compact
                            text: qsTr("New")
                            type: "tonal"
                            enabled: !agent.busy && !agent.actionBusy && !agent.options.length
                            onClicked: agent.newChat()
                        }
                    }
                }

                Item {
                    id: conversationArea
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    ListView {
                        id: history
                        anchors.fill: parent
                        anchors.leftMargin: window.pageMargin
                        anchors.rightMargin: window.pageMargin
                        anchors.topMargin: 18 * window.scale
                        anchors.bottomMargin: 14 * window.scale
                        clip: true
                        spacing: 12 * window.scale
                        model: messages
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        delegate: Item {
                            id: messageDelegate
                            required property string speaker
                            required property string body
                            readonly property bool fromUser: speaker === "user"
                            width: history.width
                            implicitHeight: messageSurface.implicitHeight

                            Item {
                                id: messageSurface
                                width: Math.min(
                                    messageDelegate.fromUser
                                        ? messageDelegate.width * 0.76
                                        : messageDelegate.width,
                                    window.contentMaxWidth)
                                implicitHeight: messageContent.implicitHeight
                                    + (messageDelegate.fromUser ? 22 : 12) * window.scale
                                anchors.right: messageDelegate.fromUser ? parent.right : undefined
                                anchors.left: messageDelegate.fromUser ? undefined : parent.left

                                Rectangle {
                                    anchors.fill: parent
                                    visible: messageDelegate.fromUser
                                    radius: 20 * window.scale
                                    color: MeoTheme.primaryContainer
                                }

                                Rectangle {
                                    visible: !messageDelegate.fromUser
                                    anchors.left: parent.left
                                    anchors.top: parent.top
                                    anchors.bottom: parent.bottom
                                    width: 3 * window.scale
                                    radius: width / 2
                                    color: MeoTheme.primary
                                    opacity: 0.72
                                }

                                ColumnLayout {
                                    id: messageContent
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.leftMargin: messageDelegate.fromUser
                                        ? 14 * window.scale
                                        : 16 * window.scale
                                    anchors.rightMargin: 14 * window.scale
                                    anchors.topMargin: messageDelegate.fromUser
                                        ? 10 * window.scale
                                        : 4 * window.scale
                                    spacing: 4 * window.scale

                                    Text {
                                        text: messageDelegate.fromUser ? qsTr("You") : qsTr("Meo AI")
                                        color: messageDelegate.fromUser
                                            ? MeoTheme.contentOnPrimaryContainer
                                            : MeoTheme.primary
                                        font.pixelSize: MeoTheme.labelSmall.size * window.scale
                                        font.weight: Font.DemiBold
                                        opacity: 0.9
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        text: messageDelegate.body
                                        textFormat: Text.PlainText
                                        wrapMode: Text.Wrap
                                        color: messageDelegate.fromUser
                                            ? MeoTheme.contentOnPrimaryContainer
                                            : MeoTheme.contentOnSurface
                                        font.pixelSize: MeoTheme.bodyLarge.size * window.scale
                                        font.weight: MeoTheme.bodyLarge.weight
                                        lineHeight: 1.34
                                    }
                                }
                            }
                        }
                    }

                    MeoCard {
                        id: emptyHero
                        visible: messages.count === 0
                        width: Math.min(parent.width - 2 * window.pageMargin, 680 * window.scale)
                        anchors.centerIn: parent
                        type: "filled"
                        compact: false

                        contentItem: ColumnLayout {
                            spacing: 14 * window.scale

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 16 * window.scale

                                MeoAiMark {
                                    Layout.preferredWidth: 62 * window.scale
                                    Layout.preferredHeight: 62 * window.scale
                                    Layout.alignment: Qt.AlignTop
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 4 * window.scale

                                    Text {
                                        Layout.fillWidth: true
                                        text: qsTr("What are we working on?")
                                        color: MeoTheme.contentOnSurface
                                        font.pixelSize: MeoTheme.headlineSmall.size * window.scale
                                        font.weight: Font.DemiBold
                                        wrapMode: Text.Wrap
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        text: agent.serviceMode
                                            ? qsTr("Ask normally. Meo AI can surface useful context as compact cards and will stop before actions that need approval.")
                                            : qsTr("Chat is available in compatibility mode. Some newer AgentService surfaces are unavailable.")
                                        color: MeoTheme.contentOnSurfaceVariant
                                        font.pixelSize: MeoTheme.bodyMedium.size * window.scale
                                        wrapMode: Text.Wrap
                                    }
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.max(1, window.scale)
                                color: MeoTheme.outlineVariant
                                opacity: 0.48
                            }

                            Flow {
                                Layout.fillWidth: true
                                spacing: 8 * window.scale

                                MeoButton {
                                    text: qsTr("Help with code")
                                    type: "tonal"
                                    onClicked: window.submit(qsTr("Help me work on my current coding project."))
                                }

                                MeoButton {
                                    text: qsTr("Check my system")
                                    type: "tonal"
                                    onClicked: window.submit(qsTr("Help me diagnose my MeoArch system safely."))
                                }

                                MeoButton {
                                    text: qsTr("Show capabilities")
                                    type: "tonal"
                                    onClicked: window.submit(qsTr("What can you help me do in MeoArch?"))
                                }
                            }
                        }
                    }
                }

                Item {
                    id: presentationShelf
                    visible: presentationCards.count > 0
                    Layout.fillWidth: true
                    Layout.leftMargin: window.pageMargin
                    Layout.rightMargin: window.pageMargin
                    Layout.bottomMargin: visible ? 10 * window.scale : 0
                    Layout.preferredHeight: visible
                        ? Math.min(172 * window.scale, cardRow.implicitHeight + 2 * window.scale)
                        : 0

                    Flickable {
                        anchors.fill: parent
                        clip: true
                        contentWidth: cardRow.width
                        contentHeight: height
                        boundsBehavior: Flickable.StopAtBounds
                        flickableDirection: Flickable.HorizontalFlick

                        Row {
                            id: cardRow
                            height: parent.height
                            spacing: 10 * window.scale

                            Repeater {
                                model: presentationCards

                                delegate: MeoCard {
                                    required property string cardId
                                    required property string kind
                                    required property string title
                                    required property string subtitle
                                    required property string cardValue
                                    required property string detail

                                    width: window.compact
                                        ? Math.min(presentationShelf.width, 330 * window.scale)
                                        : 286 * window.scale
                                    height: Math.max(132 * window.scale, presentationShelf.height)
                                    type: "filled"
                                    compact: true

                                    contentItem: ColumnLayout {
                                        spacing: 6 * window.scale

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 8 * window.scale

                                            Rectangle {
                                                Layout.preferredWidth: 8 * window.scale
                                                Layout.preferredHeight: 8 * window.scale
                                                radius: width / 2
                                                color: MeoTheme.primary
                                            }

                                            Text {
                                                Layout.fillWidth: true
                                                text: title
                                                color: MeoTheme.contentOnSurface
                                                font.pixelSize: MeoTheme.titleSmall.size * window.scale
                                                font.weight: Font.DemiBold
                                                elide: Text.ElideRight
                                            }

                                            Text {
                                                text: window.cardKindLabel(kind)
                                                color: MeoTheme.contentOnSurfaceVariant
                                                font.pixelSize: MeoTheme.labelSmall.size * window.scale
                                                font.weight: Font.DemiBold
                                                opacity: 0.72
                                            }
                                        }

                                        Text {
                                            visible: subtitle.length > 0
                                            Layout.fillWidth: true
                                            text: subtitle
                                            color: MeoTheme.contentOnSurfaceVariant
                                            font.pixelSize: MeoTheme.labelSmall.size * window.scale
                                            elide: Text.ElideRight
                                        }

                                        Text {
                                            visible: cardValue.length > 0
                                            Layout.fillWidth: true
                                            text: cardValue
                                            color: MeoTheme.primary
                                            font.pixelSize: MeoTheme.headlineSmall.size * window.scale
                                            font.weight: Font.DemiBold
                                            wrapMode: Text.Wrap
                                            maximumLineCount: 2
                                            elide: Text.ElideRight
                                        }

                                        Text {
                                            visible: detail.length > 0
                                            Layout.fillWidth: true
                                            text: detail
                                            textFormat: Text.PlainText
                                            wrapMode: Text.Wrap
                                            color: MeoTheme.contentOnSurfaceVariant
                                            font.pixelSize: MeoTheme.bodySmall.size * window.scale
                                            maximumLineCount: 3
                                            elide: Text.ElideRight
                                        }

                                        Item { Layout.fillHeight: true }
                                    }
                                }
                            }
                        }
                    }
                }

                MeoCard {
                    visible: agent.options.length > 0 && window.pendingToolDisplay.length > 0
                    Layout.fillWidth: true
                    Layout.leftMargin: window.pageMargin
                    Layout.rightMargin: window.pageMargin
                    Layout.bottomMargin: 10 * window.scale
                    type: "outlined"
                    selected: true
                    compact: true

                    contentItem: RowLayout {
                        spacing: 14 * window.scale

                        Rectangle {
                            Layout.preferredWidth: 4 * window.scale
                            Layout.fillHeight: true
                            radius: width / 2
                            color: MeoTheme.primary
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 8 * window.scale

                            Text {
                                Layout.fillWidth: true
                                text: qsTr("Confirmation required")
                                color: MeoTheme.contentOnSurface
                                font.pixelSize: MeoTheme.titleSmall.size * window.scale
                                font.weight: Font.DemiBold
                            }

                            Text {
                                Layout.fillWidth: true
                                text: window.pendingToolDisplay
                                textFormat: Text.PlainText
                                wrapMode: Text.Wrap
                                color: MeoTheme.contentOnSurfaceVariant
                                font.pixelSize: MeoTheme.bodyMedium.size * window.scale
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8 * window.scale

                                Repeater {
                                    model: agent.options

                                    delegate: MeoButton {
                                        required property var modelData
                                        required property int index
                                        Layout.fillWidth: true
                                        text: modelData.title
                                        type: index === 0 ? "tonal" : "filled"
                                        enabled: !agent.actionBusy && (agent.serviceMode || !agent.busy)
                                        onClicked: agent.choose(index)
                                    }
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    id: composerBand
                    Layout.fillWidth: true
                    color: MeoTheme.surface
                    implicitHeight: composerShell.implicitHeight + 18 * window.scale

                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        height: Math.max(1, window.scale)
                        color: MeoTheme.outlineVariant
                        opacity: 0.28
                    }

                    Rectangle {
                        id: composerShell
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.leftMargin: window.pageMargin
                        anchors.rightMargin: window.pageMargin
                        anchors.verticalCenter: parent.verticalCenter
                        implicitHeight: composerColumn.implicitHeight + 16 * window.scale
                        radius: 24 * window.scale
                        color: MeoTheme.surfaceContainerLow
                        border.width: Math.max(1, window.scale)
                        border.color: composer.activeFocus
                            ? MeoTheme.primary
                            : MeoTheme.outlineVariant

                        ColumnLayout {
                            id: composerColumn
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 8 * window.scale
                            spacing: 4 * window.scale

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8 * window.scale

                                MeoTextArea {
                                    id: composer
                                    label: qsTr("Message Meo AI")
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 68 * window.scale
                                    enabled: !agent.busy && !agent.actionBusy && !agent.options.length

                                    Keys.onPressed: function(event) {
                                        if (event.key === Qt.Key_Return
                                                && (event.modifiers & Qt.ControlModifier)) {
                                            window.submit(text)
                                            event.accepted = true
                                        }
                                    }
                                }

                                MeoButton {
                                    text: agent.busy ? qsTr("Working") : qsTr("Send")
                                    type: "filled"
                                    loading: agent.busy || agent.actionBusy
                                    enabled: !agent.busy && !agent.actionBusy
                                        && !agent.options.length && composer.text.trim().length > 0
                                    onClicked: window.submit(composer.text)
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true

                                Text {
                                    Layout.fillWidth: true
                                    text: agent.options.length
                                        ? qsTr("Choose an option above to continue.")
                                        : (agent.busy
                                            ? qsTr("Meo AI is working…")
                                            : qsTr("Ctrl+Enter to send"))
                                    color: MeoTheme.contentOnSurfaceVariant
                                    font.pixelSize: MeoTheme.labelSmall.size * window.scale
                                    opacity: 0.75
                                }

                                Text {
                                    visible: !window.compact
                                    text: agent.serviceMode
                                        ? qsTr("Local-first AgentService")
                                        : qsTr("Compatibility mode")
                                    color: MeoTheme.contentOnSurfaceVariant
                                    font.pixelSize: MeoTheme.labelSmall.size * window.scale
                                    opacity: 0.64
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Popup {
        id: modelRolesPopup
        modal: true
        focus: true
        x: Math.round((window.width - width) / 2)
        y: Math.round((window.height - height) / 2)
        width: Math.min(660 * window.scale, window.width - 32 * window.scale)
        height: Math.min(680 * window.scale, window.height - 32 * window.scale)
        padding: 0
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            radius: 26 * window.scale
            color: MeoTheme.surfaceContainerLow
            border.width: Math.max(1, window.scale)
            border.color: MeoTheme.outlineVariant
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20 * window.scale
            spacing: 12 * window.scale

            RowLayout {
                Layout.fillWidth: true
                spacing: 12 * window.scale

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1 * window.scale

                    Text {
                        Layout.fillWidth: true
                        text: qsTr("Models by job")
                        color: MeoTheme.contentOnSurface
                        font.pixelSize: MeoTheme.headlineSmall.size * window.scale
                        font.weight: Font.DemiBold
                    }

                    Text {
                        Layout.fillWidth: true
                        text: qsTr("Use strong models where they matter and small models for background work.")
                        color: MeoTheme.contentOnSurfaceVariant
                        font.pixelSize: MeoTheme.bodySmall.size * window.scale
                        wrapMode: Text.Wrap
                    }
                }

                Rectangle {
                    implicitWidth: roleCountLabel.implicitWidth + 18 * window.scale
                    implicitHeight: 30 * window.scale
                    radius: 11 * window.scale
                    color: MeoTheme.primaryContainer

                    Text {
                        id: roleCountLabel
                        anchors.centerIn: parent
                        text: qsTr("%1 roles").arg(agent.modelRoles.length)
                        color: MeoTheme.contentOnPrimaryContainer
                        font.pixelSize: MeoTheme.labelSmall.size * window.scale
                        font.weight: Font.DemiBold
                    }
                }

                MeoButton {
                    text: qsTr("Close")
                    type: "tonal"
                    onClicked: modelRolesPopup.close()
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(1, window.scale)
                color: MeoTheme.outlineVariant
                opacity: 0.48
            }

            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true

                Column {
                    width: parent.width
                    spacing: 9 * window.scale

                    Repeater {
                        model: agent.modelRoles

                        delegate: MeoCard {
                            required property var modelData
                            width: parent.width
                            type: "outlined"
                            compact: true

                            contentItem: ColumnLayout {
                                spacing: 7 * window.scale

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8 * window.scale

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 0

                                        Text {
                                            Layout.fillWidth: true
                                            text: String(modelData.label || modelData.role_id || "")
                                            color: MeoTheme.contentOnSurface
                                            font.pixelSize: MeoTheme.titleSmall.size * window.scale
                                            font.weight: Font.DemiBold
                                            elide: Text.ElideRight
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: modelData.workload === "auxiliary"
                                                ? qsTr("Background workload")
                                                : qsTr("Primary workload")
                                            color: MeoTheme.primary
                                            font.pixelSize: MeoTheme.labelSmall.size * window.scale
                                            font.weight: Font.DemiBold
                                        }
                                    }

                                    Text {
                                        text: modelData.runtime_supported
                                            ? qsTr("Active")
                                            : qsTr("Saved")
                                        color: modelData.runtime_supported
                                            ? MeoTheme.primary
                                            : MeoTheme.contentOnSurfaceVariant
                                        font.pixelSize: MeoTheme.labelSmall.size * window.scale
                                        font.weight: Font.DemiBold
                                    }
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: String(modelData.description || "")
                                    wrapMode: Text.Wrap
                                    color: MeoTheme.contentOnSurfaceVariant
                                    font.pixelSize: MeoTheme.bodySmall.size * window.scale
                                }

                                ComboBox {
                                    Layout.fillWidth: true
                                    model: agent.models
                                    textRole: "label"
                                    valueRole: "model_id"
                                    enabled: agent.models.length > 0 && !agent.actionBusy
                                    currentIndex: window.modelIndex(
                                        String(modelData.preferred_model_id
                                            || modelData.fallback_model_id
                                            || ""))

                                    onActivated: function(index) {
                                        if (index < 0 || index >= agent.models.length)
                                            return
                                        agent.setModelRole(
                                            String(modelData.role_id || ""),
                                            String(agent.models[index].model_id || ""))
                                    }
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: modelData.runtime_supported
                                        ? qsTr("Independent routing is active for this role.")
                                        : qsTr("Preference saved · independent runtime routing is not active yet.")
                                    color: MeoTheme.contentOnSurfaceVariant
                                    font.pixelSize: MeoTheme.labelSmall.size * window.scale
                                    opacity: 0.78
                                    wrapMode: Text.Wrap
                                }
                            }
                        }
                    }
                }
            }

            MeoCard {
                Layout.fillWidth: true
                type: "filled"
                compact: true

                contentItem: RowLayout {
                    spacing: 10 * window.scale

                    Rectangle {
                        Layout.preferredWidth: 8 * window.scale
                        Layout.preferredHeight: 8 * window.scale
                        radius: width / 2
                        color: MeoTheme.primary
                    }

                    Text {
                        Layout.fillWidth: true
                        text: qsTr("Judge can classify and rank, but it never approves privileged actions. System authority stays with Router policy and explicit confirmation.")
                        wrapMode: Text.Wrap
                        color: MeoTheme.contentOnSurfaceVariant
                        font.pixelSize: MeoTheme.labelSmall.size * window.scale
                    }
                }
            }
        }
    }
}

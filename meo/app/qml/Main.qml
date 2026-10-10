import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0

ApplicationWindow {
    id: window
    objectName: "meoAiMainWindow"
    width: 1180
    height: 780
    minimumWidth: 620
    minimumHeight: 500
    visible: true
    title: qsTr("Meo AI")
    color: MeoTheme.surface

    readonly property real scale: MeoTheme.globalScale
    readonly property bool compact: width < 760 * scale
    readonly property bool showSidebar: width >= 1040 * scale
    readonly property real pageMargin: compact ? 14 * scale : 24 * scale
    readonly property real contentMaxWidth: 780 * scale
    readonly property real composerMaxWidth: 820 * scale
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
        Qt.callLater(function() {
            if (cardFlick.contentWidth > cardFlick.width)
                cardFlick.contentX = Math.max(0, cardFlick.contentWidth - cardFlick.width)
        })
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
            messages.append({speaker: role, body: text})
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
            window.upsertPresentationCard(card)
        }

        function onResetChat() {
            messages.clear()
            presentationCards.clear()
            window.pendingToolDisplay = ""
        }
    }

    Shortcut {
        sequence: "Ctrl+N"
        enabled: !agent.busy && !agent.actionBusy && !agent.options.length
        onActivated: agent.newChat()
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            id: sidebar
            objectName: "meoAiSidebar"
            visible: window.showSidebar
            Layout.fillHeight: true
            Layout.preferredWidth: 248 * window.scale
            color: MeoTheme.surfaceContainerLow

            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: 12 * window.scale
                anchors.rightMargin: 12 * window.scale
                anchors.topMargin: 14 * window.scale
                anchors.bottomMargin: 14 * window.scale
                spacing: 8 * window.scale

                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 6 * window.scale
                    Layout.rightMargin: 4 * window.scale
                    Layout.bottomMargin: 8 * window.scale
                    spacing: 10 * window.scale

                    MeoAiMark {
                        Layout.preferredWidth: 28 * window.scale
                        Layout.preferredHeight: 28 * window.scale
                    }

                    MeoText {
                        Layout.fillWidth: true
                        text: qsTr("Meo AI")
                        typeRole: "title"
                        typeSize: "small"
                        color: MeoTheme.contentOnSurface
                    }
                }

                MeoButton {
                    Layout.fillWidth: true
                    text: qsTr("New chat")
                    type: "tonal"
                    size: "s"
                    enabled: !agent.busy && !agent.actionBusy && !agent.options.length
                    onClicked: agent.newChat()
                }

                MeoText {
                    Layout.fillWidth: true
                    Layout.leftMargin: 8 * window.scale
                    Layout.topMargin: 12 * window.scale
                    text: qsTr("Chats")
                    typeRole: "label"
                    typeSize: "small"
                    color: MeoTheme.contentOnSurfaceVariant
                    opacity: 0.72
                }

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 48 * window.scale
                    radius: 14 * window.scale
                    color: MeoTheme.surfaceContainer

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 12 * window.scale
                        anchors.rightMargin: 10 * window.scale
                        spacing: 10 * window.scale

                        Rectangle {
                            Layout.preferredWidth: 6 * window.scale
                            Layout.preferredHeight: 6 * window.scale
                            radius: width / 2
                            color: MeoTheme.primary
                        }

                        MeoText {
                            Layout.fillWidth: true
                            text: qsTr("Current chat")
                            typeRole: "body"
                            typeSize: "medium"
                            color: MeoTheme.contentOnSurface
                            elide: Text.ElideRight
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                MeoButton {
                    visible: agent.serviceMode
                    Layout.fillWidth: true
                    text: qsTr("Models by job")
                    type: "text"
                    size: "s"
                    enabled: !agent.actionBusy && !agent.metadataBusy
                    onClicked: modelRolesPopup.open()
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 9 * window.scale
                    Layout.rightMargin: 9 * window.scale
                    spacing: 8 * window.scale

                    Rectangle {
                        Layout.preferredWidth: 6 * window.scale
                        Layout.preferredHeight: 6 * window.scale
                        radius: width / 2
                        color: agent.serviceMode ? MeoTheme.primary : MeoTheme.contentOnSurfaceVariant
                    }

                    MeoText {
                        Layout.fillWidth: true
                        text: agent.serviceMode ? qsTr("Local service") : qsTr("Compatibility mode")
                        typeRole: "label"
                        typeSize: "small"
                        color: MeoTheme.contentOnSurfaceVariant
                        opacity: 0.74
                        elide: Text.ElideRight
                    }
                }
            }
        }

        Item {
            id: mainPane
            Layout.fillWidth: true
            Layout.fillHeight: true

            Rectangle {
                id: compactHeader
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: 54 * window.scale
                color: MeoTheme.surface

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: window.pageMargin
                    anchors.rightMargin: window.pageMargin
                    spacing: 8 * window.scale

                    MeoAiMark {
                        visible: !window.showSidebar
                        Layout.preferredWidth: 26 * window.scale
                        Layout.preferredHeight: 26 * window.scale
                    }

                    MeoText {
                        Layout.fillWidth: true
                        text: messages.count ? qsTr("Current chat") : qsTr("Meo AI")
                        typeRole: "label"
                        typeSize: "medium"
                        color: MeoTheme.contentOnSurfaceVariant
                        elide: Text.ElideRight
                    }

                    MeoText {
                        visible: agent.busy && !window.compact
                        text: qsTr("Working…")
                        typeRole: "label"
                        typeSize: "small"
                        color: MeoTheme.primary
                    }

                    MeoButton {
                        visible: !window.showSidebar && agent.serviceMode
                        text: qsTr("Models")
                        type: "text"
                        size: "xs"
                        enabled: !agent.actionBusy && !agent.metadataBusy
                        onClicked: modelRolesPopup.open()
                    }

                    MeoButton {
                        visible: !window.showSidebar
                        text: qsTr("New")
                        type: "text"
                        size: "xs"
                        enabled: !agent.busy && !agent.actionBusy && !agent.options.length
                        onClicked: agent.newChat()
                    }
                }
            }

            ListView {
                id: history
                objectName: "meoAiHistory"
                anchors.top: compactHeader.bottom
                anchors.bottom: confirmationSurface.visible
                    ? confirmationSurface.top
                    : (presentationShelf.visible ? presentationShelf.top : composerShell.top)
                anchors.bottomMargin: 14 * window.scale
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
                    required property string body
                    readonly property bool fromUser: speaker === "user"
                    width: history.width
                    implicitHeight: messageBody.implicitHeight

                    Item {
                        id: messageBody
                        width: messageDelegate.fromUser
                            ? Math.min(messageDelegate.width * 0.72, 560 * window.scale)
                            : messageDelegate.width
                        implicitHeight: messageText.implicitHeight
                            + (messageDelegate.fromUser ? 20 : 4) * window.scale
                        anchors.right: messageDelegate.fromUser ? parent.right : undefined
                        anchors.left: messageDelegate.fromUser ? undefined : parent.left

                        Rectangle {
                            anchors.fill: parent
                            visible: messageDelegate.fromUser
                            radius: 18 * window.scale
                            color: MeoTheme.surfaceContainer
                        }

                        MeoText {
                            id: messageText
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.leftMargin: messageDelegate.fromUser ? 14 * window.scale : 0
                            anchors.rightMargin: messageDelegate.fromUser ? 14 * window.scale : 0
                            anchors.topMargin: messageDelegate.fromUser ? 10 * window.scale : 2 * window.scale
                            text: messageDelegate.body
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            typeRole: "body"
                            typeSize: "medium"
                            fontScaleOverride: 1.04
                            color: MeoTheme.contentOnSurface
                        }
                    }
                }
            }

            ColumnLayout {
                id: emptyIntro
                visible: messages.count === 0
                width: Math.min(parent.width - 2 * window.pageMargin, 720 * window.scale)
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: composerShell.top
                anchors.bottomMargin: 24 * window.scale
                spacing: 8 * window.scale

                MeoText {
                    Layout.fillWidth: true
                    text: qsTr("What can I help you build?")
                    typeRole: "title"
                    typeSize: "big"
                    color: MeoTheme.contentOnSurface
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                }

                MeoText {
                    Layout.fillWidth: true
                    text: agent.serviceMode
                        ? qsTr("Ask a question, plan something, or hand off a task.")
                        : qsTr("Chat is available in compatibility mode.")
                    typeRole: "body"
                    typeSize: "medium"
                    color: MeoTheme.contentOnSurfaceVariant
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                }
            }

            Item {
                id: presentationShelf
                objectName: "meoAiPresentationShelf"
                visible: presentationCards.count > 0
                width: Math.min(parent.width - 2 * window.pageMargin, window.composerMaxWidth)
                height: visible ? 108 * window.scale : 0
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: composerShell.top
                anchors.bottomMargin: visible ? 10 * window.scale : 0

                Flickable {
                    id: cardFlick
                    anchors.fill: parent
                    clip: true
                    contentWidth: cardRow.width
                    contentHeight: height
                    boundsBehavior: Flickable.StopAtBounds
                    flickableDirection: Flickable.HorizontalFlick
                    interactive: contentWidth > width

                    Row {
                        id: cardRow
                        height: parent.height
                        spacing: 8 * window.scale

                        Repeater {
                            model: presentationCards

                            delegate: Rectangle {
                                required property string cardId
                                required property string kind
                                required property string title
                                required property string subtitle
                                required property string cardValue
                                required property string detail

                                width: window.compact
                                    ? Math.min(presentationShelf.width * 0.86, 260 * window.scale)
                                    : 246 * window.scale
                                height: presentationShelf.height
                                radius: 18 * window.scale
                                color: MeoTheme.surfaceContainerLowest
                                border.width: Math.max(1, window.scale)
                                border.color: MeoTheme.outlineVariant

                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 12 * window.scale
                                    spacing: 2 * window.scale

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 7 * window.scale

                                        Rectangle {
                                            Layout.preferredWidth: 6 * window.scale
                                            Layout.preferredHeight: 6 * window.scale
                                            radius: width / 2
                                            color: MeoTheme.primary
                                        }

                                        MeoText {
                                            Layout.fillWidth: true
                                            text: title
                                            typeRole: "label"
                                            typeSize: "medium"
                                            color: MeoTheme.contentOnSurface
                                            elide: Text.ElideRight
                                        }
                                    }

                                    MeoText {
                                        visible: cardValue.length > 0
                                        Layout.fillWidth: true
                                        text: cardValue
                                        typeRole: "title"
                                        typeSize: "small"
                                        color: MeoTheme.contentOnSurface
                                        maximumLineCount: 1
                                        elide: Text.ElideRight
                                    }

                                    MeoText {
                                        visible: (detail.length > 0 || subtitle.length > 0)
                                        Layout.fillWidth: true
                                        text: detail.length ? detail : subtitle
                                        typeRole: "body"
                                        typeSize: "small"
                                        color: MeoTheme.contentOnSurfaceVariant
                                        maximumLineCount: 2
                                        elide: Text.ElideRight
                                        wrapMode: Text.Wrap
                                    }

                                    Item { Layout.fillHeight: true }
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                id: confirmationSurface
                visible: agent.options.length > 0 && window.pendingToolDisplay.length > 0
                width: Math.min(parent.width - 2 * window.pageMargin, window.composerMaxWidth)
                implicitHeight: confirmationColumn.implicitHeight + 24 * window.scale
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: presentationShelf.visible ? presentationShelf.top : composerShell.top
                anchors.bottomMargin: visible ? 10 * window.scale : 0
                radius: 18 * window.scale
                color: MeoTheme.surfaceContainerLow
                border.width: Math.max(1, window.scale)
                border.color: MeoTheme.outlineVariant

                ColumnLayout {
                    id: confirmationColumn
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 12 * window.scale
                    spacing: 8 * window.scale

                    MeoText {
                        Layout.fillWidth: true
                        text: qsTr("Confirmation required")
                        typeRole: "label"
                        typeSize: "medium"
                        color: MeoTheme.contentOnSurface
                    }

                    MeoText {
                        Layout.fillWidth: true
                        text: window.pendingToolDisplay
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        typeRole: "body"
                        typeSize: "small"
                        color: MeoTheme.contentOnSurfaceVariant
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
                                type: index === 0 ? "outlined" : "filled"
                                size: "s"
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
                implicitHeight: composerColumn.implicitHeight + 20 * window.scale
                anchors.horizontalCenter: parent.horizontalCenter
                y: messages.count === 0
                    ? Math.round(Math.min(parent.height - height - 78 * window.scale,
                                         parent.height * 0.49))
                    : Math.round(parent.height - height - 18 * window.scale)
                radius: 24 * window.scale
                color: MeoTheme.surfaceContainerLowest
                border.width: Math.max(1, window.scale)
                border.color: composer.activeFocus ? MeoTheme.primary : MeoTheme.outlineVariant

                Behavior on y {
                    enabled: !MeoTheme.reduceMotion
                    NumberAnimation {
                        duration: MeoTheme.motionDurationSpatialMedium
                        easing.type: Easing.OutCubic
                    }
                }

                ColumnLayout {
                    id: composerColumn
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 10 * window.scale
                    spacing: 8 * window.scale

                    TextArea {
                        id: composer
                        objectName: "meoAiComposer"
                        Layout.fillWidth: true
                        Layout.preferredHeight: messages.count === 0 ? 74 * window.scale : 58 * window.scale
                        enabled: !agent.busy && !agent.actionBusy && !agent.options.length
                        placeholderText: qsTr("How can I help?")
                        wrapMode: TextEdit.Wrap
                        selectByMouse: true
                        leftPadding: 4 * window.scale
                        rightPadding: 4 * window.scale
                        topPadding: 4 * window.scale
                        bottomPadding: 4 * window.scale
                        color: MeoTheme.contentOnSurface
                        font.family: MeoTheme.typefacePlain
                        font.pixelSize: MeoTheme.bodyLarge.size * MeoTheme.fontScale * window.scale
                        background: null

                        Keys.onPressed: function(event) {
                            const enter = event.key === Qt.Key_Return || event.key === Qt.Key_Enter
                            const newline = event.modifiers & Qt.ShiftModifier
                            if (enter && !newline && !inputMethodComposing) {
                                window.submit(text)
                                event.accepted = true
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6 * window.scale

                        MeoButton {
                            visible: agent.serviceMode
                            text: qsTr("Models")
                            type: "text"
                            size: "xs"
                            enabled: !agent.actionBusy && !agent.metadataBusy
                            onClicked: modelRolesPopup.open()
                        }

                        MeoText {
                            visible: !window.compact
                            Layout.maximumWidth: 220 * window.scale
                            text: window.selectedModelLabel.length
                                ? window.selectedModelLabel
                                : (agent.serviceMode ? qsTr("Local service") : qsTr("Compatibility"))
                            typeRole: "label"
                            typeSize: "small"
                            color: MeoTheme.contentOnSurfaceVariant
                            opacity: 0.68
                            elide: Text.ElideRight
                        }

                        Item { Layout.fillWidth: true }

                        MeoText {
                            visible: agent.busy && !window.compact
                            text: qsTr("Working…")
                            typeRole: "label"
                            typeSize: "small"
                            color: MeoTheme.contentOnSurfaceVariant
                        }

                        MeoButton {
                            text: agent.busy && agent.serviceMode ? qsTr("Stop") : qsTr("Send")
                            type: "filled"
                            size: "xs"
                            enabled: agent.busy && agent.serviceMode
                                ? !agent.actionBusy
                                : (!agent.busy && !agent.actionBusy && !agent.options.length
                                    && composer.text.trim().length > 0)
                            onClicked: {
                                if (agent.busy && agent.serviceMode)
                                    agent.cancel()
                                else
                                    window.submit(composer.text)
                            }
                        }
                    }
                }
            }

            Flow {
                id: quickActions
                visible: messages.count === 0 && !agent.busy && !agent.options.length
                width: Math.min(parent.width - 2 * window.pageMargin, 650 * window.scale)
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: composerShell.bottom
                anchors.topMargin: 12 * window.scale
                spacing: 6 * window.scale

                MeoButton {
                    text: qsTr("Code")
                    type: "text"
                    size: "xs"
                    onClicked: window.submit(qsTr("Help me work on my current coding project."))
                }

                MeoButton {
                    text: qsTr("Plan")
                    type: "text"
                    size: "xs"
                    onClicked: window.submit(qsTr("Help me plan this task before we start."))
                }

                MeoButton {
                    text: qsTr("System")
                    type: "text"
                    size: "xs"
                    onClicked: window.submit(qsTr("Help me diagnose my MeoArch system safely."))
                }
            }
        }
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

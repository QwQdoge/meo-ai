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
    readonly property real pageMargin: Math.max(16 * scale, Math.min(32 * scale, width * 0.025))
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

    ListModel { id: messages }

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
        function onResetChat() {
            messages.clear()
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
            Layout.preferredWidth: window.wideSidebar ? 248 * window.scale : 88 * window.scale
            color: MeoTheme.surfaceContainer

            Rectangle {
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                width: Math.max(1, window.scale)
                color: MeoTheme.outlineVariant
                opacity: 0.55
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16 * window.scale
                spacing: 16 * window.scale

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10 * window.scale

                    MeoAiMark {
                        Layout.preferredWidth: 40 * window.scale
                        Layout.preferredHeight: 40 * window.scale
                    }
                    ColumnLayout {
                        visible: window.wideSidebar
                        Layout.fillWidth: true
                        spacing: 0
                        Text {
                            text: qsTr("Meo AI")
                            color: MeoTheme.contentOnSurface
                            font.pixelSize: MeoTheme.titleLarge.size * window.scale
                            font.weight: MeoTheme.titleLarge.weight
                        }
                        Text {
                            text: qsTr("Modern · Expressive · Open")
                            color: MeoTheme.contentOnSurfaceVariant
                            font.pixelSize: MeoTheme.labelMedium.size * window.scale
                            font.weight: MeoTheme.labelMedium.weight
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
                    spacing: 8 * window.scale
                    Text {
                        visible: window.wideSidebar
                        text: qsTr("Workspace")
                        color: MeoTheme.contentOnSurfaceVariant
                        font.pixelSize: MeoTheme.labelMedium.size * window.scale
                        font.weight: Font.DemiBold
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 52 * window.scale
                        radius: 26 * window.scale
                        color: MeoTheme.primaryContainer
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 18 * window.scale
                            anchors.rightMargin: 18 * window.scale
                            spacing: 10 * window.scale
                            Text {
                                text: "●"
                                color: MeoTheme.primary
                                font.pixelSize: 13 * window.scale
                            }
                            Text {
                                visible: window.wideSidebar
                                Layout.fillWidth: true
                                text: qsTr("Current chat")
                                color: MeoTheme.contentOnPrimaryContainer
                                font.pixelSize: MeoTheme.labelLarge.size * window.scale
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 6 * window.scale
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 44 * window.scale
                        radius: 22 * window.scale
                        color: MeoTheme.surface
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 14 * window.scale
                            anchors.rightMargin: 14 * window.scale
                            spacing: 8 * window.scale
                            Rectangle {
                                width: 8 * window.scale
                                height: width
                                radius: width / 2
                                color: agent.serviceMode ? MeoTheme.primary : MeoTheme.contentOnSurfaceVariant
                            }
                            Text {
                                visible: window.wideSidebar
                                Layout.fillWidth: true
                                text: agent.serviceMode ? qsTr("AgentService") : qsTr("Compatibility")
                                color: MeoTheme.contentOnSurfaceVariant
                                font.pixelSize: MeoTheme.labelMedium.size * window.scale
                                elide: Text.ElideRight
                            }
                        }
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
                    Layout.fillWidth: true
                    Layout.preferredHeight: 72 * window.scale
                    color: MeoTheme.surface

                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: Math.max(1, window.scale)
                        color: MeoTheme.outlineVariant
                        opacity: 0.48
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: window.pageMargin
                        anchors.rightMargin: window.pageMargin
                        spacing: 12 * window.scale

                        MeoAiMark {
                            visible: window.compact
                            Layout.preferredWidth: 34 * window.scale
                            Layout.preferredHeight: 34 * window.scale
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1 * window.scale
                            Text {
                                text: qsTr("Meo AI")
                                color: MeoTheme.contentOnSurface
                                font.pixelSize: MeoTheme.titleLarge.size * window.scale
                                font.weight: MeoTheme.titleLarge.weight
                            }
                            Text {
                                text: agent.status
                                color: MeoTheme.contentOnSurfaceVariant
                                font.pixelSize: MeoTheme.labelMedium.size * window.scale
                                font.weight: MeoTheme.labelMedium.weight
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                        }

                        Rectangle {
                            implicitWidth: modeLabel.implicitWidth + 28 * window.scale
                            implicitHeight: 34 * window.scale
                            radius: height / 2
                            color: MeoTheme.surfaceContainer
                            border.width: Math.max(1, window.scale)
                            border.color: MeoTheme.outlineVariant
                            Text {
                                id: modeLabel
                                anchors.centerIn: parent
                                text: agent.serviceMode
                                    ? (window.selectedModelLabel.length ? window.selectedModelLabel : qsTr("Local service"))
                                    : qsTr("Legacy API")
                                color: MeoTheme.contentOnSurfaceVariant
                                font.pixelSize: MeoTheme.labelMedium.size * window.scale
                                font.weight: Font.DemiBold
                            }
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
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    ListView {
                        id: history
                        anchors.fill: parent
                        anchors.leftMargin: window.pageMargin
                        anchors.rightMargin: window.pageMargin
                        anchors.topMargin: 18 * window.scale
                        anchors.bottomMargin: 18 * window.scale
                        clip: true
                        spacing: 14 * window.scale
                        model: messages
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        delegate: Item {
                            id: messageDelegate
                            required property string speaker
                            required property string body
                            readonly property bool fromUser: speaker === "user"
                            width: history.width
                            implicitHeight: messageBubble.implicitHeight + 2 * window.scale

                            Rectangle {
                                id: messageBubble
                                width: Math.min(messageDelegate.width * 0.82, 760 * window.scale)
                                implicitHeight: messageContent.implicitHeight + 24 * window.scale
                                anchors.right: messageDelegate.fromUser ? parent.right : undefined
                                anchors.left: messageDelegate.fromUser ? undefined : parent.left
                                radius: 24 * window.scale
                                color: messageDelegate.fromUser ? MeoTheme.primaryContainer : MeoTheme.surfaceContainer

                                ColumnLayout {
                                    id: messageContent
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: 12 * window.scale
                                    spacing: 5 * window.scale

                                    Text {
                                        text: messageDelegate.fromUser ? qsTr("You") : qsTr("Meo AI")
                                        color: messageDelegate.fromUser
                                            ? MeoTheme.contentOnPrimaryContainer
                                            : MeoTheme.primary
                                        font.pixelSize: MeoTheme.labelMedium.size * window.scale
                                        font.weight: Font.DemiBold
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
                                        lineHeight: 1.35
                                    }
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        visible: messages.count === 0
                        width: Math.min(parent.width - 48 * window.scale, 620 * window.scale)
                        anchors.centerIn: parent
                        spacing: 16 * window.scale

                        MeoAiMark {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.preferredWidth: 72 * window.scale
                            Layout.preferredHeight: 72 * window.scale
                        }
                        Text {
                            Layout.fillWidth: true
                            text: qsTr("What can I help with?")
                            horizontalAlignment: Text.AlignHCenter
                            color: MeoTheme.contentOnSurface
                            font.pixelSize: MeoTheme.headlineMedium.size * window.scale
                            font.weight: MeoTheme.headlineMedium.weight
                        }
                        Text {
                            Layout.fillWidth: true
                            text: agent.serviceMode
                                ? qsTr("Ask about MeoArch, your project, or a system task. Actions that need approval will stop and ask first.")
                                : qsTr("The compatibility backend is active. Chat works, but the new AgentService features are not all available.")
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.Wrap
                            color: MeoTheme.contentOnSurfaceVariant
                            font.pixelSize: MeoTheme.bodyMedium.size * window.scale
                            font.weight: MeoTheme.bodyMedium.weight
                        }
                        Flow {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.preferredWidth: Math.min(560 * window.scale, parent.width)
                            spacing: 8 * window.scale
                            MeoButton {
                                text: qsTr("What can you do?")
                                type: "tonal"
                                onClicked: window.submit(qsTr("What can you help me do in MeoArch?"))
                            }
                            MeoButton {
                                text: qsTr("Check my system")
                                type: "tonal"
                                onClicked: window.submit(qsTr("Help me diagnose my MeoArch system safely."))
                            }
                            MeoButton {
                                text: qsTr("Help with code")
                                type: "tonal"
                                onClicked: window.submit(qsTr("Help me work on my current coding project."))
                            }
                        }
                    }
                }

                MeoCard {
                    visible: agent.options.length > 0 && window.pendingToolDisplay.length > 0
                    Layout.fillWidth: true
                    Layout.leftMargin: window.pageMargin
                    Layout.rightMargin: window.pageMargin
                    Layout.bottomMargin: 12 * window.scale
                    type: "filled"

                    contentItem: ColumnLayout {
                        spacing: 10 * window.scale
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10 * window.scale
                            Rectangle {
                                width: 10 * window.scale
                                height: width
                                radius: width / 2
                                color: MeoTheme.primary
                            }
                            Text {
                                Layout.fillWidth: true
                                text: qsTr("Confirmation required")
                                color: MeoTheme.contentOnSurface
                                font.pixelSize: MeoTheme.titleMedium.size * window.scale
                                font.weight: Font.DemiBold
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: window.pendingToolDisplay
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            color: MeoTheme.contentOnSurfaceVariant
                            font.pixelSize: MeoTheme.bodyMedium.size * window.scale
                            font.weight: MeoTheme.bodyMedium.weight
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

                Rectangle {
                    Layout.fillWidth: true
                    color: MeoTheme.surface
                    implicitHeight: composerShell.implicitHeight + 20 * window.scale

                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        height: Math.max(1, window.scale)
                        color: MeoTheme.outlineVariant
                        opacity: 0.42
                    }

                    Rectangle {
                        id: composerShell
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.leftMargin: window.pageMargin
                        anchors.rightMargin: window.pageMargin
                        anchors.verticalCenter: parent.verticalCenter
                        implicitHeight: composerColumn.implicitHeight + 18 * window.scale
                        radius: 28 * window.scale
                        color: MeoTheme.surfaceContainer
                        border.width: Math.max(1, window.scale)
                        border.color: MeoTheme.outlineVariant

                        ColumnLayout {
                            id: composerColumn
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 10 * window.scale
                            spacing: 6 * window.scale

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10 * window.scale
                                MeoTextArea {
                                    id: composer
                                    label: qsTr("Message Meo AI")
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 84 * window.scale
                                    enabled: !agent.busy && !agent.actionBusy && !agent.options.length
                                    Keys.onPressed: function(event) {
                                        if (event.key === Qt.Key_Return && (event.modifiers & Qt.ControlModifier)) {
                                            window.submit(text)
                                            event.accepted = true
                                        }
                                    }
                                }
                                MeoButton {
                                    text: qsTr("Send")
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
                                        : (agent.busy ? qsTr("Meo AI is working…") : qsTr("Ctrl+Enter to send"))
                                    color: MeoTheme.contentOnSurfaceVariant
                                    font.pixelSize: MeoTheme.labelSmall.size * window.scale
                                }
                                Text {
                                    text: agent.serviceMode ? qsTr("AgentService preview") : qsTr("Compatibility mode")
                                    color: MeoTheme.contentOnSurfaceVariant
                                    font.pixelSize: MeoTheme.labelSmall.size * window.scale
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

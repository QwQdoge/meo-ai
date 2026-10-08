import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0

ApplicationWindow {
    id: window
    width: 1000; height: 720
    minimumWidth: 480; minimumHeight: 560
    visible: true
    title: qsTr("Meo AI · Preview")
    color: MeoTheme.background
    readonly property real margin: MeoTheme.windowPageMargin(width)
    property string pendingToolDisplay: ""

    ListModel { id: messages }
    Connections {
        target: agent
        function onMessage(role, text) { messages.append({speaker: role, body: text}); history.positionViewAtEnd() }
        function onDelta(text) {
            if (messages.count) {
                const n = messages.count - 1
                messages.setProperty(n, "body", messages.get(n).body + text)
                history.positionViewAtEnd()
            }
        }
        function onToolEvent(event) {
            const text = event.display_text
            window.pendingToolDisplay = typeof text === "string" ? text : ""
        }
        function onResetChat() {
            messages.clear()
            window.pendingToolDisplay = ""
        }
    }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: window.margin
        spacing: 16 * MeoTheme.globalScale
        RowLayout {
            MeoAiMark { width: 36 * MeoTheme.globalScale; height: width }
            Label { text: qsTr("Meo AI"); font.pixelSize: MeoTheme.headlineMedium.size * MeoTheme.globalScale; font.weight: MeoTheme.headlineMedium.weight; color: MeoTheme.onSurface; Layout.fillWidth: true }
            MeoButton {
                visible: agent.serviceMode && agent.busy
                text: qsTr("Stop")
                type: "tonal"
                enabled: !agent.actionBusy
                onClicked: agent.cancel()
            }
            MeoButton { text: qsTr("New chat"); type: "tonal"; enabled: !agent.busy && !agent.actionBusy && !agent.options.length; onClicked: agent.newChat() }
        }
        Label { text: agent.status; wrapMode: Text.Wrap; color: MeoTheme.onSurfaceVariant; font.pixelSize: MeoTheme.bodyMedium.size * MeoTheme.globalScale; font.weight: MeoTheme.bodyMedium.weight; Layout.fillWidth: true }
        ListView {
            id: history
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true; spacing: 12 * MeoTheme.globalScale
            model: messages
            ScrollBar.vertical: ScrollBar {}
            delegate: MeoCard {
                required property string speaker
                required property string body
                width: history.width
                type: "filled"
                contentItem: ColumnLayout {
                    Label { text: speaker === "user" ? qsTr("You") : qsTr("Meo AI"); font.pixelSize: MeoTheme.labelLarge.size * MeoTheme.globalScale; font.weight: MeoTheme.labelLarge.weight; color: MeoTheme.primary }
                    Label { text: body; textFormat: Text.PlainText; wrapMode: Text.Wrap; font.pixelSize: MeoTheme.bodyLarge.size * MeoTheme.globalScale; font.weight: MeoTheme.bodyLarge.weight; color: MeoTheme.onSurface; Layout.fillWidth: true }
                }
            }
            Label {
                visible: messages.count === 0
                anchors.centerIn: parent
                text: agent.serviceMode
                    ? qsTr("Ask about your project or MeoArch.\nAgentService mode uses typed request and tool-decision events.")
                    : qsTr("Ask about your project or MeoArch.\n/models · /model · /tools · /skill\nLegacy Newelle API compatibility mode.")
                horizontalAlignment: Text.AlignHCenter
                font.pixelSize: MeoTheme.bodyLarge.size * MeoTheme.globalScale; font.weight: MeoTheme.bodyLarge.weight; color: MeoTheme.onSurfaceVariant
            }
        }
        MeoCard {
            visible: agent.options.length > 0 && window.pendingToolDisplay.length > 0
            Layout.fillWidth: true
            type: "filled"
            contentItem: ColumnLayout {
                spacing: 6 * MeoTheme.globalScale
                Label {
                    text: qsTr("Confirmation required")
                    font.pixelSize: MeoTheme.labelLarge.size * MeoTheme.globalScale
                    font.weight: MeoTheme.labelLarge.weight
                    color: MeoTheme.primary
                }
                Label {
                    text: window.pendingToolDisplay
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    font.pixelSize: MeoTheme.bodyMedium.size * MeoTheme.globalScale
                    font.weight: MeoTheme.bodyMedium.weight
                    color: MeoTheme.onSurface
                }
            }
        }
        Repeater {
            model: agent.options
            delegate: MeoButton {
                required property var modelData
                required property int index
                text: modelData.title
                type: "tonal"
                enabled: !agent.actionBusy && (agent.serviceMode || !agent.busy)
                Layout.fillWidth: true
                onClicked: agent.choose(index)
            }
        }
        RowLayout {
            MeoTextArea {
                id: composer
                label: qsTr("Message")
                Layout.fillWidth: true
                Layout.preferredHeight: 120 * MeoTheme.globalScale
                enabled: !agent.busy && !agent.actionBusy && !agent.options.length
                Keys.onPressed: event => {
                    if (event.key === Qt.Key_Return && (event.modifiers & Qt.ControlModifier)) {
                        agent.send(text); text = ""; event.accepted = true
                    }
                }
            }
            MeoButton {
                text: qsTr("Send"); loading: agent.busy || agent.actionBusy
                enabled: !agent.busy && !agent.actionBusy && !agent.options.length && composer.text.trim().length > 0
                onClicked: { agent.send(composer.text); composer.text = "" }
            }
        }
    }
}

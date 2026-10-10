import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0

Rectangle {
    id: root
    objectName: "meoAiDetailsPane"
    property var metadata: ({})
    property var toolEvents: []
    property var memoryState: ({})
    property var memories: []
    property var resources: []
    property var skills: []
    property bool ready: false
    property bool busy: false
    property int tab: 0
    readonly property real uiScale: MeoTheme.globalScale
    signal closeRequested()
    signal manageMemoryRequested()
    signal attachRequested()
    signal discardRequested(string resourceId)
    signal modelsRequested()
    signal controlsRequested()
    signal selectedTabRequested(int selectedTab)
    radius: 26 * uiScale
    color: MeoTheme.surfaceContainerLow

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12 * root.uiScale
        spacing: 12 * root.uiScale
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 8 * root.uiScale
            MeoText {
                Layout.fillWidth: true
                text: [qsTr("Response details"), qsTr("Memory"), qsTr("Resources"), qsTr("AI settings")][root.tab]
                typeRole: "title"
                typeSize: "small"
                color: MeoTheme.contentOnSurface
            }
            MeoIconButton {
                icon.name: "right_panel_close"
                type: "standard"
                size: "xs"
                Accessible.name: qsTr("Close details")
                ToolTip.visible: hovered
                ToolTip.text: Accessible.name
                onClicked: root.closeRequested()
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 4 * root.uiScale
            Repeater {
                model: [qsTr("Response"), qsTr("Memory"), qsTr("Files"), qsTr("Settings")]
                delegate: MeoButton {
                    required property string modelData
                    required property int index
                    Layout.fillWidth: true
                    text: modelData
                    size: "xs"
                    type: root.tab === index ? "tonal" : "text"
                    onClicked: root.selectedTabRequested(index)
                }
            }
        }
        ResponseContent {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.tab === 0 && (Object.keys(root.metadata).length > 0 || root.toolEvents.length > 0)
            metadata: root.metadata
            toolEvents: root.toolEvents
            showHeading: false
        }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.tab === 0 && Object.keys(root.metadata).length === 0 && root.toolEvents.length === 0
            spacing: 12 * root.uiScale
            Item { Layout.fillHeight: true }
            MeoIcon { Layout.alignment: Qt.AlignHCenter; icon: "data_exploration"; size: 36; color: MeoTheme.primary }
            MeoText {
                Layout.fillWidth: true
                text: qsTr("A little more context")
                typeRole: "title"; typeSize: "small"
                horizontalAlignment: Text.AlignHCenter
                color: MeoTheme.contentOnSurface
            }
            MeoText {
                Layout.fillWidth: true
                Layout.leftMargin: 14 * root.uiScale; Layout.rightMargin: 14 * root.uiScale
                text: qsTr("Model usage, tool activity and sources will appear here as your conversation unfolds.")
                wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
                color: MeoTheme.contentOnSurfaceVariant
            }
            Item { Layout.fillHeight: true }
        }
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.tab !== 0
            clip: true
            ColumnLayout {
                width: parent.width
                spacing: 10 * root.uiScale
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: overview.implicitHeight + 32 * root.uiScale
                    radius: 20 * root.uiScale
                    color: MeoTheme.surfaceContainerLowest
                    ColumnLayout {
                        id: overview
                        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                        anchors.margins: 16 * root.uiScale
                        spacing: 12 * root.uiScale
                        MeoIcon {
                            icon: root.tab === 1 ? "neurology" : root.tab === 2 ? "attach_file" : "tune"
                            color: MeoTheme.primary; size: 28
                        }
                        MeoText {
                            Layout.fillWidth: true
                            text: root.tab === 1 ? qsTr("Remember what matters")
                                  : root.tab === 2 ? qsTr("Context for your next message") : qsTr("Your AI, your choices")
                            typeRole: "title"; typeSize: "small"
                            color: MeoTheme.contentOnSurface
                            wrapMode: Text.Wrap
                        }
                        MeoText {
                            Layout.fillWidth: true
                            text: root.tab === 1 ? (root.memoryState.supported
                                      ? qsTr("Review, edit or remove what Meo AI remembers.")
                                      : qsTr("Managed memory is unavailable for the current service."))
                                  : root.tab === 2 ? qsTr("Add long text to this conversation. Only the items you attach are sent with your next message.")
                                  : qsTr("Choose models by job and adjust the controls offered by your current service.")
                            wrapMode: Text.Wrap
                            color: MeoTheme.contentOnSurfaceVariant
                        }
                        MeoButton {
                            Layout.fillWidth: true
                            text: root.tab === 1 ? qsTr("Manage memory") : root.tab === 2 ? qsTr("Attach text") : qsTr("Models by job")
                            type: "tonal"; size: "s"
                            enabled: !root.busy && (root.tab !== 1 || !!root.memoryState.supported)
                            onClicked: {
                                if (root.tab === 1) root.manageMemoryRequested()
                                else if (root.tab === 2) root.attachRequested()
                                else root.modelsRequested()
                            }
                        }
                        MeoButton {
                            visible: root.tab === 3
                            Layout.fillWidth: true
                            text: qsTr("AI controls"); type: "outlined"; size: "s"
                            enabled: !root.busy
                            onClicked: root.controlsRequested()
                        }
                    }
                }
                Repeater {
                    model: root.tab === 1 ? root.memories : root.tab === 2 ? root.resources : root.skills
                    delegate: Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: itemContent.implicitHeight + 24 * root.uiScale
                        radius: 18 * root.uiScale
                        color: MeoTheme.surfaceContainerLowest
                        ColumnLayout {
                            id: itemContent
                            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                            anchors.margins: 12 * root.uiScale
                            spacing: 6 * root.uiScale
                            MeoText {
                                Layout.fillWidth: true
                                text: String(modelData.text || modelData.name || modelData.label || "")
                                wrapMode: Text.Wrap
                                color: MeoTheme.contentOnSurface
                            }
                            MeoText {
                                Layout.fillWidth: true
                                text: root.tab === 1 ? String(modelData.scope || "")
                                      : root.tab === 2 ? String(modelData.state || "")
                                      : (modelData.enabled ? qsTr("Enabled") : qsTr("Disabled"))
                                typeRole: "label"; typeSize: "small"
                                color: MeoTheme.contentOnSurfaceVariant
                            }
                            MeoButton {
                                visible: root.tab === 2
                                text: qsTr("Remove attachment"); type: "text"; size: "xs"
                                enabled: !root.busy
                                onClicked: root.discardRequested(String(modelData.resource_id || ""))
                            }
                        }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: 6 * root.uiScale
            Rectangle {
                width: 7 * root.uiScale; height: width; radius: width / 2
                color: root.ready ? MeoTheme.primary : MeoTheme.outline
            }
            MeoText {
                Layout.fillWidth: true
                text: root.ready ? qsTr("Local service connected") : qsTr("Local service not connected")
                typeRole: "label"; typeSize: "small"
                color: MeoTheme.contentOnSurfaceVariant
                elide: Text.ElideRight
            }
        }
    }
}

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0

Drawer {
    id: root
    objectName: "meoAiMobileNavigationDrawer"

    property real uiScale: MeoTheme.globalScale
    property string primaryMode: "chat"
    property var destinations: []
    property bool deviceReady: false

    signal modeSelected(string mode)
    signal newChatRequested()
    signal settingsRequested()

    edge: Qt.LeftEdge
    modal: true
    interactive: true
    dragMargin: 28 * root.uiScale
    width: Math.min(344 * root.uiScale, parent ? parent.width * 0.88 : 344 * root.uiScale)
    height: parent ? parent.height : 720 * root.uiScale
    padding: 0

    background: Rectangle {
        color: MeoTheme.surfaceContainerLow
        radius: 0
    }

    contentItem: ColumnLayout {
        anchors.fill: parent
        anchors.margins: 14 * root.uiScale
        spacing: 8 * root.uiScale

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 8 * root.uiScale
            Layout.bottomMargin: 18 * root.uiScale
            spacing: 12 * root.uiScale

            AiLogo {
                Layout.preferredWidth: 40 * root.uiScale
                Layout.preferredHeight: 40 * root.uiScale
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2 * root.uiScale
                MeoText {
                    text: qsTr("Meo AI")
                    typeRole: "title"
                    typeSize: "medium"
                    color: MeoTheme.contentOnSurface
                }
                MeoText {
                    Layout.fillWidth: true
                    text: qsTr("A little help. More possibility.")
                    elide: Text.ElideRight
                    typeRole: "label"
                    typeSize: "small"
                    color: MeoTheme.contentOnSurfaceVariant
                }
            }

            MeoIconButton {
                objectName: "meoAiMobileNavClose"
                icon.name: "close"
                type: "standard"
                size: "xs"
                Accessible.name: qsTr("Close navigation")
                onClicked: root.close()
            }
        }

        NavigationButton {
            objectName: "meoAiMobileNewChat"
            Layout.fillWidth: true
            text: qsTr("New chat")
            icon.name: "add"
            type: "filled"
            size: "s"
            Accessible.name: qsTr("New chat")
            onClicked: {
                root.close()
                root.newChatRequested()
            }
        }

        Repeater {
            model: root.destinations
            delegate: NavigationButton {
                required property var modelData
                objectName: "meoAiMobileNav-" + modelData.action
                Layout.fillWidth: true
                text: modelData.label
                icon.name: modelData.icon
                type: root.primaryMode === modelData.action ? "tonal" : "text"
                size: "s"
                Accessible.name: modelData.label
                onClicked: {
                    root.close()
                    root.modeSelected(String(modelData.action))
                }
            }
        }

        MeoText {
            visible: root.primaryMode === "chat"
            Layout.topMargin: 22 * root.uiScale
            Layout.leftMargin: 12 * root.uiScale
            text: qsTr("This conversation")
            typeRole: "label"
            typeSize: "small"
            color: MeoTheme.contentOnSurfaceVariant
        }

        NavigationButton {
            visible: root.primaryMode === "chat"
            Layout.fillWidth: true
            text: qsTr("Current chat")
            icon.name: "chat"
            type: "tonal"
            size: "s"
            onClicked: {
                root.close()
                root.modeSelected("chat")
            }
        }

        Item { Layout.fillHeight: true }

        NavigationButton {
            objectName: "meoAiMobileSettings"
            Layout.fillWidth: true
            text: qsTr("AI settings")
            icon.name: "tune"
            type: "text"
            size: "s"
            Accessible.name: qsTr("AI settings")
            onClicked: {
                root.close()
                root.settingsRequested()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 76 * root.uiScale
            radius: 20 * root.uiScale
            color: MeoTheme.surfaceContainer

            RowLayout {
                anchors.fill: parent
                anchors.margins: 12 * root.uiScale
                spacing: 12 * root.uiScale

                MeoIcon { icon: "computer"; size: 28; color: MeoTheme.primary }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4 * root.uiScale
                    MeoText {
                        text: qsTr("This computer")
                        typeRole: "label"
                        typeSize: "medium"
                        color: MeoTheme.contentOnSurface
                    }
                    MeoText {
                        text: root.deviceReady ? qsTr("Service connected") : qsTr("Service not connected")
                        typeRole: "label"
                        typeSize: "small"
                        color: MeoTheme.contentOnSurfaceVariant
                    }
                }

                Rectangle {
                    width: 7 * root.uiScale
                    height: width
                    radius: width / 2
                    color: root.deviceReady ? MeoTheme.primary : MeoTheme.outline
                }
            }
        }
    }
}

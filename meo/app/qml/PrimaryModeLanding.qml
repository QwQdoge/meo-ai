import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0

Item {
    id: root
    objectName: "meoAiModeLanding-" + modeKey

    property string modeKey: ""
    property string title: ""
    property string description: ""
    property string iconName: "auto_awesome"
    property bool showDeviceTarget: false
    property bool deviceReady: false
    property real uiScale: MeoTheme.globalScale

    ColumnLayout {
        width: Math.min(parent.width - 48 * root.uiScale, 720 * root.uiScale)
        anchors.centerIn: parent
        spacing: 16 * root.uiScale

        Rectangle {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 64 * root.uiScale
            Layout.preferredHeight: 64 * root.uiScale
            radius: 22 * root.uiScale
            color: MeoTheme.secondaryContainer

            MeoIcon {
                anchors.centerIn: parent
                icon: root.iconName
                size: 32
                color: MeoTheme.primary
            }
        }

        MeoText {
            Layout.fillWidth: true
            text: root.title
            typeRole: "title"
            typeSize: "big"
            color: MeoTheme.contentOnSurface
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
        }

        MeoText {
            Layout.fillWidth: true
            text: root.description
            typeRole: "body"
            typeSize: "medium"
            color: MeoTheme.contentOnSurfaceVariant
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
        }

        Rectangle {
            objectName: root.modeKey === "work" ? "meoAiWorkTarget" : ""
            visible: root.showDeviceTarget
            Layout.fillWidth: true
            implicitHeight: targetRow.implicitHeight + 28 * root.uiScale
            radius: 22 * root.uiScale
            color: MeoTheme.surfaceContainerLow
            border.width: Math.max(1, root.uiScale)
            border.color: MeoTheme.outlineVariant

            RowLayout {
                id: targetRow
                anchors.fill: parent
                anchors.margins: 14 * root.uiScale
                spacing: 12 * root.uiScale

                Rectangle {
                    Layout.preferredWidth: 44 * root.uiScale
                    Layout.preferredHeight: 44 * root.uiScale
                    radius: 15 * root.uiScale
                    color: MeoTheme.surfaceContainer
                    MeoIcon {
                        anchors.centerIn: parent
                        icon: "computer"
                        size: 24
                        color: MeoTheme.primary
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2 * root.uiScale
                    MeoText {
                        text: qsTr("This computer")
                        typeRole: "title"
                        typeSize: "small"
                        color: MeoTheme.contentOnSurface
                    }
                    MeoText {
                        Layout.fillWidth: true
                        text: root.deviceReady
                            ? qsTr("Local AgentService is ready for Work")
                            : qsTr("Local AgentService is not connected")
                        typeRole: "body"
                        typeSize: "small"
                        color: MeoTheme.contentOnSurfaceVariant
                        wrapMode: Text.Wrap
                    }
                }

                Rectangle {
                    Layout.preferredWidth: 9 * root.uiScale
                    Layout.preferredHeight: 9 * root.uiScale
                    radius: width / 2
                    color: root.deviceReady ? MeoTheme.primary : MeoTheme.outline
                }
            }
        }

        MeoText {
            visible: root.showDeviceTarget
            Layout.fillWidth: true
            text: qsTr("Remote computers will appear here after Meo Account device relay is connected. Privileged actions still require explicit approval.")
            typeRole: "label"
            typeSize: "small"
            color: MeoTheme.contentOnSurfaceVariant
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
        }
    }
}

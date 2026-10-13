import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0

Popup {
    id: root
    objectName: "meo.aiResponseDetails"
    property var metadata: ({})
    property real uiScale: MeoTheme.globalScale
    modal: true
    focus: true
    width: Math.min(660 * uiScale, parent ? parent.width - 28 * uiScale : 660 * uiScale)
    height: Math.min(720 * uiScale, parent ? parent.height - 28 * uiScale : 720 * uiScale)
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    background: Rectangle {
        radius: 24 * root.uiScale
        color: MeoTheme.surface
        border.width: Math.max(1, root.uiScale)
        border.color: MeoTheme.outlineVariant
    }

    contentItem: ColumnLayout {
        anchors.fill: parent
        spacing: 10 * root.uiScale

        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 20 * root.uiScale
            Layout.rightMargin: 20 * root.uiScale
            Layout.topMargin: 18 * root.uiScale
            spacing: 8 * root.uiScale

            MeoText {
                Layout.fillWidth: true
                text: qsTr("Response details")
                typeRole: "title"
                typeSize: "medium"
                color: MeoTheme.contentOnSurface
            }

            MeoButton {
                text: qsTr("Close")
                type: "text"
                size: "xs"
                onClicked: root.close()
            }
        }

        ResponseExecutionSummary {
            metadata: root.metadata
            uiScale: root.uiScale
            Layout.fillWidth: true
            Layout.leftMargin: 20 * root.uiScale
            Layout.rightMargin: 20 * root.uiScale
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.leftMargin: 20 * root.uiScale
            Layout.rightMargin: 20 * root.uiScale
            Layout.preferredHeight: Math.max(1, root.uiScale)
            color: MeoTheme.outlineVariant
            opacity: 0.42
        }

        ResponseContent {
            Layout.fillWidth: true
            Layout.fillHeight: true
            metadata: root.metadata
            uiScale: root.uiScale
            showHeading: false
            onCloseRequested: root.close()
        }
    }
}

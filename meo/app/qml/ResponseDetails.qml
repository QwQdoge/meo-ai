import QtQuick
import QtQuick.Controls
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
    contentItem: ResponseContent {
        metadata: root.metadata
        uiScale: root.uiScale
        onCloseRequested: root.close()
    }
}

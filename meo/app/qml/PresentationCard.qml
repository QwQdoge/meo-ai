import QtQuick
import QtQuick.Layouts
import MeoUI 1.0

Rectangle {
    id: root
    property string kind: "info"
    property string title: ""
    property string subtitle: ""
    property string cardValue: ""
    property string detail: ""
    readonly property real uiScale: MeoTheme.globalScale
    readonly property color accent: kind === "system" ? MeoTheme.tertiary : MeoTheme.primary
    implicitHeight: content.implicitHeight + 32 * uiScale
    radius: 22 * uiScale
    color: kind === "metric" ? MeoTheme.primaryContainer
           : kind === "system" ? MeoTheme.tertiaryContainer : MeoTheme.surfaceContainerLow
    ColumnLayout {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 16 * root.uiScale
        spacing: 8 * root.uiScale
        RowLayout {
            Layout.fillWidth: true
            spacing: 10 * root.uiScale
            MeoIcon {
                icon: root.kind === "metric" ? "memory" : root.kind === "system" ? "folder_open"
                      : root.kind === "status" ? "check_circle" : root.kind === "file" ? "description" : "auto_awesome"
                size: 24
                color: root.accent
            }
            MeoText {
                Layout.fillWidth: true
                text: root.title
                typeRole: "label"
                typeSize: "medium"
                color: MeoTheme.contentOnSurface
                elide: Text.ElideRight
            }
        }
        MeoText {
            Layout.fillWidth: true
            visible: root.cardValue.length > 0
            text: root.cardValue
            typeRole: "title"
            typeSize: "medium"
            color: MeoTheme.contentOnSurface
            wrapMode: Text.Wrap
        }
        MeoText {
            Layout.fillWidth: true
            text: root.detail.length ? root.detail : root.subtitle
            typeRole: "body"
            typeSize: "small"
            color: MeoTheme.contentOnSurfaceVariant
            wrapMode: Text.Wrap
            maximumLineCount: 4
            elide: Text.ElideRight
        }
    }
}

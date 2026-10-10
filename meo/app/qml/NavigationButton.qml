import QtQuick
import QtQuick.Layouts
import MeoUI 1.0

MeoButton {
    id: root
    leftPadding: 12 * themeGlobalScale
    rightPadding: 12 * themeGlobalScale
    contentItem: RowLayout {
        spacing: 12 * root.themeGlobalScale
        MeoIcon {
            icon: root.icon.name
            size: root.iconSize
            color: root.textColor
            opacity: root.enabled ? 1 : 0.38
        }
        MeoText {
            Layout.fillWidth: true
            visible: root.text.length > 0
            text: root.text
            typeRole: "label"; typeSize: "large"
            color: root.textColor
            elide: Text.ElideRight
        }
    }
}

import QtQuick
import MeoUI 1.0

Item {
    id: root
    objectName: "meo.aiLogo"

    // Stable presentation boundary for AI branding. Main.qml only depends on
    // AiLogo, so a future icon, animated mark, account avatar, or theme-selected
    // asset can replace this implementation without touching the chat layout.
    readonly property string assetKey: "meo.aiLogo"
    property string accessibleName: qsTr("Meo AI")

    MeoAiMark {
        anchors.fill: parent
    }
}

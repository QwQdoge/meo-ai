import QtQuick
import QtQuick.Controls
import MeoUI 1.0
import "ProductNavigation.js" as Navigation

Item {
    id: root
    objectName: "meoAiMobileNavigationOverlay"

    property var hostWindow: null
    readonly property real uiScale: hostWindow ? hostWindow.scale : MeoTheme.globalScale
    readonly property bool compact: !!hostWindow && hostWindow.compact

    anchors.fill: parent
    visible: compact
    z: 1000

    Rectangle {
        id: menuButtonSurface
        objectName: "meoAiMobileMenuSurface"
        visible: root.compact
        width: 40 * root.uiScale
        height: width
        radius: width / 2
        x: 8 * root.uiScale + (root.hostWindow ? root.hostWindow.pageMargin : 18 * root.uiScale)
        y: 18 * root.uiScale
        color: MeoTheme.surfaceContainerLowest

        MeoIconButton {
            id: menuButton
            objectName: "meoAiMobileMenuButton"
            anchors.fill: parent
            icon.name: "menu"
            type: "standard"
            size: "xs"
            Accessible.name: qsTr("Open navigation")
            ToolTip.visible: hovered
            ToolTip.text: Accessible.name
            onClicked: mobileDrawer.open()
        }
    }

    MobileNavigationDrawer {
        id: mobileDrawer
        parent: Overlay.overlay
        uiScale: root.uiScale
        interactive: root.compact
        primaryMode: root.hostWindow ? String(root.hostWindow.primaryMode || "chat") : "chat"
        deviceReady: !!agent.agentState.ready
        destinations: Navigation.destinations("primary")
        secondaryDestinations: Navigation.destinations("secondary")

        onModeSelected: function(mode) {
            if (root.hostWindow)
                root.hostWindow.selectPrimaryMode(mode)
        }
        onNewChatRequested: {
            if (!root.hostWindow)
                return
            root.hostWindow.selectPrimaryMode("chat")
            agent.newChat()
        }
        onSettingsRequested: {
            if (root.hostWindow)
                root.hostWindow.openInspector(3)
        }
    }
}

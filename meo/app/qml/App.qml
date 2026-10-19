import QtQuick

Main {
    id: appWindow

    LiveRecoverySetup {
        id: liveSetup
        anchors.fill: parent
        z: 200
        visible: liveRecovery
        onStartRequested: (language, goal) => {
            visible = false
            appWindow.startLiveRecoveryChat(language, goal)
        }
    }

    MobileNavigationOverlay {
        anchors.fill: parent
        hostWindow: appWindow
    }
}

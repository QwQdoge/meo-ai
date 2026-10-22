import QtQuick

Main {
    id: appWindow

    // The recovery setup only exists in a Live session; elsewhere the context
    // properties it needs are not provided, so do not even instantiate it.
    Loader {
        id: liveSetup
        anchors.fill: parent
        z: 200
        active: typeof liveRecovery !== "undefined" && liveRecovery
        visible: active
        sourceComponent: LiveRecoverySetup {
            onStartRequested: (language, goal) => {
                liveSetup.active = false
                appWindow.startLiveRecoveryChat(language, goal)
            }
        }
    }

    MobileNavigationOverlay {
        anchors.fill: parent
        hostWindow: appWindow
    }
}

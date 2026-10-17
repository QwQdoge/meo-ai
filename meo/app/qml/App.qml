import QtQuick

Main {
    id: appWindow

    MobileNavigationOverlay {
        anchors.fill: parent
        hostWindow: appWindow
    }
}

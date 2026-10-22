// Dynamic color for Meo AI: when the Meo desktop's Material color provider (Meo.System, from
// meo-kde) is installed, its wallpaper-derived scheme is applied to MeoUI and follows wallpaper and
// light/dark changes. Without it the stock MeoUI palette stays. Loaded through a Loader, so a
// missing plugin never stops the app from starting.
import QtQuick
import Meo.System 1.0 as MeoSystem
import MeoUI 1.0

QtObject {
    id: root

    readonly property bool darkMode: Qt.styleHints.colorScheme === Qt.ColorScheme.Dark

    function provider() {
        return typeof MeoSystem.MaterialColors === "undefined" ? null : MeoSystem.MaterialColors
    }

    function sync() {
        MeoTheme.isDarkMode = darkMode
        const p = provider()
        const scheme = p ? p.currentScheme(darkMode) : null
        if (scheme && p)
            MeoTheme.applyDynamicColorScheme(scheme, p.sourceId())
        else
            MeoTheme.clearDynamicColorScheme()
    }

    onDarkModeChanged: sync()

    property Connections providerConnections: Connections {
        target: root.provider()
        ignoreUnknownSignals: true
        function onSchemeChanged() { root.sync() }
    }

    Component.onCompleted: sync()
}

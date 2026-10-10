import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0

ScrollView {
    id: root
    clip: true
    readonly property real uiScale: MeoTheme.globalScale
    readonly property var data: usage.dashboard || ({})
    readonly property var summary: data.summary || ({})
    readonly property var breakdown: data.token_breakdown || ({})
    readonly property var models: data.models || []
    readonly property var projects: data.projects || []
    readonly property var sources: data.sources || []
    readonly property var daily: data.daily || []

    function compactNumber(value) {
        const n = Number(value || 0)
        if (n >= 1000000000) return (n / 1000000000).toFixed(n >= 10000000000 ? 0 : 1) + "B"
        if (n >= 1000000) return (n / 1000000).toFixed(n >= 10000000 ? 0 : 1) + "M"
        if (n >= 1000) return (n / 1000).toFixed(n >= 10000 ? 0 : 1) + "K"
        return String(Math.round(n))
    }

    function duration(value) {
        const ms = Number(value || 0)
        if (!ms) return "—"
        const minutes = Math.round(ms / 60000)
        if (minutes < 60) return minutes + "m"
        const hours = Math.floor(minutes / 60)
        const rest = minutes % 60
        return rest ? hours + "h " + rest + "m" : hours + "h"
    }

    function sourceLabel(value) {
        if (value === "claude_code") return "Claude Code"
        if (value === "codex") return "Codex"
        if (value === "meo") return "Meo AI"
        if (value === "opencode") return "OpenCode"
        if (value === "cline") return "Cline"
        return String(value || "Other")
    }

    function heatLevel(tokens) {
        let maximum = 0
        for (let i = 0; i < daily.length; ++i) maximum = Math.max(maximum, Number(daily[i].tokens || 0))
        if (!maximum || !tokens) return 0
        const ratio = Number(tokens) / maximum
        if (ratio < 0.08) return 1
        if (ratio < 0.24) return 2
        if (ratio < 0.5) return 3
        return 4
    }

    function barWidth(tokens, list, available) {
        let maximum = 1
        for (let i = 0; i < list.length; ++i) maximum = Math.max(maximum, Number(list[i].tokens || 0))
        return Math.max(4 * uiScale, available * Number(tokens || 0) / maximum)
    }

    ColumnLayout {
        width: root.availableWidth
        spacing: 16 * root.uiScale

        RowLayout {
            Layout.fillWidth: true
            spacing: 8 * root.uiScale
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3 * root.uiScale
                MeoText {
                    Layout.fillWidth: true
                    text: qsTr("AI activity")
                    typeRole: "title"; typeSize: "medium"
                    color: MeoTheme.contentOnSurface
                }
                MeoText {
                    Layout.fillWidth: true
                    text: usage.status || qsTr("Your work across Meo AI, Codex and Claude Code")
                    typeRole: "body"; typeSize: "small"
                    color: MeoTheme.contentOnSurfaceVariant
                    wrapMode: Text.Wrap
                }
            }
            MeoIconButton {
                icon.name: "refresh"; size: "xs"; type: "standard"
                enabled: !usage.busy
                Accessible.name: qsTr("Refresh activity")
                ToolTip.visible: hovered; ToolTip.text: Accessible.name
                onClicked: usage.refresh()
            }
        }

        GridLayout {
            Layout.fillWidth: true
            columns: width > 620 * root.uiScale ? 5 : width > 360 * root.uiScale ? 2 : 1
            columnSpacing: 8 * root.uiScale
            rowSpacing: 8 * root.uiScale
            Repeater {
                model: [
                    {value: root.compactNumber(root.summary.lifetime_tokens), label: qsTr("Lifetime tokens")},
                    {value: root.compactNumber(root.summary.peak_day_tokens), label: qsTr("Peak day")},
                    {value: root.duration(root.summary.longest_session_ms), label: qsTr("Longest session")},
                    {value: String(root.summary.longest_streak || 0), label: qsTr("Best streak")},
                    {value: String(root.summary.current_streak || 0), label: qsTr("Current streak")}
                ]
                delegate: Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 82 * root.uiScale
                    radius: 18 * root.uiScale
                    color: MeoTheme.surfaceContainerLowest
                    border.width: Math.max(1, root.uiScale)
                    border.color: MeoTheme.outlineVariant
                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 12 * root.uiScale
                        spacing: 2 * root.uiScale
                        MeoText {
                            text: modelData.value
                            typeRole: "title"; typeSize: "small"
                            color: MeoTheme.contentOnSurface
                        }
                        MeoText {
                            Layout.fillWidth: true
                            text: modelData.label
                            typeRole: "label"; typeSize: "small"
                            color: MeoTheme.contentOnSurfaceVariant
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: activityColumn.implicitHeight + 28 * root.uiScale
            radius: 22 * root.uiScale
            color: MeoTheme.surfaceContainerLowest
            border.width: Math.max(1, root.uiScale)
            border.color: MeoTheme.outlineVariant
            ColumnLayout {
                id: activityColumn
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                anchors.margins: 14 * root.uiScale
                spacing: 12 * root.uiScale
                RowLayout {
                    Layout.fillWidth: true
                    MeoText { text: qsTr("Token activity"); typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurface }
                    Item { Layout.fillWidth: true }
                    MeoText {
                        text: qsTr("%1 active days").arg(root.summary.active_days || 0)
                        typeRole: "label"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant
                    }
                }
                Grid {
                    Layout.fillWidth: true
                    columns: Math.max(7, Math.floor(width / (12 * root.uiScale)))
                    spacing: 3 * root.uiScale
                    Repeater {
                        model: root.daily.slice(Math.max(0, root.daily.length - 154))
                        delegate: Rectangle {
                            required property var modelData
                            width: 9 * root.uiScale; height: width; radius: 3 * root.uiScale
                            readonly property int level: root.heatLevel(Number(modelData.tokens || 0))
                            color: level === 0 ? MeoTheme.surfaceContainerHigh
                                 : level === 1 ? MeoTheme.secondaryContainer
                                 : level === 2 ? MeoTheme.primaryContainer
                                 : level === 3 ? MeoTheme.primary
                                 : MeoTheme.contentOnPrimaryContainer
                            opacity: level === 0 ? 0.55 : level === 1 ? 0.58 : level === 2 ? 0.72 : 1
                            ToolTip.visible: heatHover.hovered
                            ToolTip.text: String(modelData.date) + " · " + root.compactNumber(modelData.tokens) + " " + qsTr("tokens")
                            HoverHandler { id: heatHover }
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: modelsColumn.implicitHeight + 28 * root.uiScale
            radius: 22 * root.uiScale
            color: MeoTheme.surfaceContainerLowest
            border.width: Math.max(1, root.uiScale); border.color: MeoTheme.outlineVariant
            ColumnLayout {
                id: modelsColumn
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                anchors.margins: 14 * root.uiScale
                spacing: 10 * root.uiScale
                MeoText { text: qsTr("Models"); typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurface }
                MeoText {
                    visible: root.models.length === 0; text: qsTr("Import local history to see model usage.")
                    color: MeoTheme.contentOnSurfaceVariant; wrapMode: Text.Wrap
                }
                Repeater {
                    model: root.models.slice(0, 6)
                    delegate: ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true; spacing: 4 * root.uiScale
                        RowLayout {
                            Layout.fillWidth: true
                            MeoText { Layout.fillWidth: true; text: String(modelData.name || "Unknown"); elide: Text.ElideRight; color: MeoTheme.contentOnSurface }
                            MeoText { text: root.compactNumber(modelData.tokens); typeRole: "label"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant }
                        }
                        Rectangle {
                            Layout.fillWidth: true; height: 6 * root.uiScale; radius: height / 2
                            color: MeoTheme.surfaceContainerHigh
                            Rectangle {
                                width: root.barWidth(modelData.tokens, root.models, parent.width)
                                height: parent.height; radius: parent.radius; color: MeoTheme.primary
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: projectsColumn.implicitHeight + 28 * root.uiScale
            radius: 22 * root.uiScale
            color: MeoTheme.surfaceContainerLowest
            border.width: Math.max(1, root.uiScale); border.color: MeoTheme.outlineVariant
            ColumnLayout {
                id: projectsColumn
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                anchors.margins: 14 * root.uiScale
                spacing: 8 * root.uiScale
                MeoText { text: qsTr("Projects"); typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurface }
                Repeater {
                    model: root.projects.slice(0, 6)
                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth: true; spacing: 8 * root.uiScale
                        MeoIcon { icon: "folder"; size: 20; color: MeoTheme.primary }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 1 * root.uiScale
                            MeoText { Layout.fillWidth: true; text: String(modelData.name || "Unassigned"); elide: Text.ElideRight; color: MeoTheme.contentOnSurface }
                            MeoText { text: qsTr("%1 sessions").arg(modelData.sessions || 0); typeRole: "label"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant }
                        }
                        MeoText { text: root.compactNumber(modelData.tokens); typeRole: "label"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: sourcesColumn.implicitHeight + 28 * root.uiScale
            radius: 22 * root.uiScale
            color: MeoTheme.surfaceContainerLowest
            border.width: Math.max(1, root.uiScale); border.color: MeoTheme.outlineVariant
            ColumnLayout {
                id: sourcesColumn
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                anchors.margins: 14 * root.uiScale
                spacing: 10 * root.uiScale
                MeoText { text: qsTr("Connected sources"); typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurface }
                Flow {
                    Layout.fillWidth: true; spacing: 7 * root.uiScale
                    Repeater {
                        model: root.sources
                        delegate: Rectangle {
                            required property var modelData
                            width: sourceRow.implicitWidth + 20 * root.uiScale; height: 36 * root.uiScale; radius: 18 * root.uiScale
                            color: MeoTheme.surfaceContainerHigh
                            Row {
                                id: sourceRow; anchors.centerIn: parent; spacing: 6 * root.uiScale
                                Rectangle { width: 7 * root.uiScale; height: width; radius: width / 2; color: MeoTheme.primary; anchors.verticalCenter: parent.verticalCenter }
                                MeoText { text: root.sourceLabel(modelData.source); typeRole: "label"; typeSize: "small"; color: MeoTheme.contentOnSurface }
                            }
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true; spacing: 8 * root.uiScale
                    MeoButton {
                        Layout.fillWidth: true
                        text: usage.busy ? qsTr("Working…") : qsTr("Import Codex & Claude Code")
                        icon.name: "download"; type: "tonal"; size: "s"
                        enabled: !usage.busy
                        onClicked: usage.importHistory()
                    }
                    MeoButton {
                        text: qsTr("Sync")
                        icon.name: "sync"; type: "outlined"; size: "s"
                        enabled: !usage.busy
                        onClicked: usage.syncNow()
                    }
                }
            }
        }

        Item { Layout.preferredHeight: 4 * root.uiScale }
    }
}

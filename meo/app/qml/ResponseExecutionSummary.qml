import QtQuick
import QtQuick.Layouts
import MeoUI 1.0

Rectangle {
    id: root

    property var metadata: ({})
    property real uiScale: MeoTheme.globalScale

    function map(value) {
        return value && typeof value === "object" ? value : ({})
    }

    function words(value) {
        const text = String(value || "").replace(/_/g, " ").trim()
        if (!text.length)
            return ""
        return text.charAt(0).toUpperCase() + text.slice(1)
    }

    readonly property var routing: map(metadata.routing)
    readonly property var coordination: map(metadata.coordination)
    readonly property var verification: map(metadata.verification)
    readonly property var tasks: Array.isArray(coordination.tasks) ? coordination.tasks : []
    readonly property bool hasRouting: Object.keys(routing).length > 0
    readonly property bool hasCoordination: Object.keys(coordination).length > 0
    readonly property bool hasVerification: Object.keys(verification).length > 0
    readonly property bool hasData: hasRouting || hasCoordination || hasVerification

    visible: hasData
    Layout.fillWidth: true
    implicitHeight: content.implicitHeight + 22 * uiScale
    radius: 18 * uiScale
    color: MeoTheme.surfaceContainerLow
    border.width: Math.max(1, uiScale)
    border.color: MeoTheme.outlineVariant

    ColumnLayout {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 11 * root.uiScale
        spacing: 7 * root.uiScale

        MeoText {
            Layout.fillWidth: true
            text: qsTr("Execution path")
            typeRole: "label"
            typeSize: "medium"
            color: MeoTheme.contentOnSurface
        }

        RowLayout {
            Layout.fillWidth: true
            visible: root.hasRouting
            spacing: 8 * root.uiScale

            MeoText {
                text: qsTr("Route")
                typeRole: "label"
                typeSize: "small"
                color: MeoTheme.contentOnSurfaceVariant
            }
            MeoText {
                Layout.fillWidth: true
                text: {
                    const role = root.words(root.routing.role_id)
                    const model = String(root.routing.model_id || "")
                    const complexity = root.words(root.routing.complexity)
                    return [role, model, complexity.length ? complexity + qsTr(" complexity") : ""]
                        .filter(function(value) { return value.length > 0 }).join(" · ")
                }
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
                typeRole: "body"
                typeSize: "small"
                color: MeoTheme.contentOnSurface
            }
        }

        RowLayout {
            Layout.fillWidth: true
            visible: root.hasCoordination
            spacing: 8 * root.uiScale

            MeoText {
                text: qsTr("Checks")
                typeRole: "label"
                typeSize: "small"
                color: MeoTheme.contentOnSurfaceVariant
            }
            MeoText {
                Layout.fillWidth: true
                text: {
                    const status = root.words(root.coordination.status)
                    const count = root.tasks.length
                    if (count > 0)
                        return qsTr("%1 focused checks · %2").arg(count).arg(status)
                    return status.length ? status : qsTr("Not used")
                }
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
                typeRole: "body"
                typeSize: "small"
                color: MeoTheme.contentOnSurface
            }
        }

        RowLayout {
            Layout.fillWidth: true
            visible: root.hasVerification
            spacing: 8 * root.uiScale

            MeoText {
                text: qsTr("Verify")
                typeRole: "label"
                typeSize: "small"
                color: MeoTheme.contentOnSurfaceVariant
            }
            MeoText {
                Layout.fillWidth: true
                text: {
                    const status = root.words(root.verification.status)
                    const repairs = Number(root.verification.repair_count || 0)
                    if (repairs > 0)
                        return qsTr("%1 · %2 repair").arg(status).arg(repairs)
                    return status.length ? status : qsTr("Not available")
                }
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
                typeRole: "body"
                typeSize: "small"
                color: MeoTheme.contentOnSurface
            }
        }
    }
}

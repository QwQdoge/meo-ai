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

    function verificationLabel() {
        const repairs = Number(verification.repair_count || 0)
        if (verification.verified === true) {
            if (repairs > 0)
                return qsTr("Verified after %1 repair").arg(repairs)
            return qsTr("Verified")
        }
        if (verification.checked === true) {
            if (repairs > 0)
                return qsTr("Not verified · %1 repair tried").arg(repairs)
            return qsTr("Not verified")
        }
        if (verification.checked === false || verification.verified === false)
            return qsTr("Not checked")

        // Compatibility with response metadata written before checked/verified
        // became first-class fields.
        const status = words(verification.status)
        return status.length ? status : qsTr("Not available")
    }

    readonly property var routing: map(metadata.routing)
    readonly property var coordination: map(metadata.coordination)
    readonly property var verification: map(metadata.verification)
    readonly property var digest: map(metadata.conversation_digest)
    readonly property var tasks: Array.isArray(coordination.tasks) ? coordination.tasks : []
    readonly property bool hasRouting: Object.keys(routing).length > 0
    readonly property bool hasCoordination: Object.keys(coordination).length > 0
    readonly property bool hasVerification: Object.keys(verification).length > 0
    readonly property bool hasDigest: Object.keys(digest).length > 0
    readonly property bool hasData: hasRouting || hasCoordination || hasVerification || hasDigest

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
                text: root.verificationLabel()
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
                typeRole: "body"
                typeSize: "small"
                color: MeoTheme.contentOnSurface
            }
        }

        Rectangle {
            Layout.fillWidth: true
            visible: root.hasDigest && root.digest.status === "completed"
            Layout.preferredHeight: Math.max(1, root.uiScale)
            color: MeoTheme.outlineVariant
            opacity: 0.32
        }

        RowLayout {
            Layout.fillWidth: true
            visible: root.hasDigest && root.digest.status === "completed"
            spacing: 8 * root.uiScale

            MeoText {
                text: qsTr("Conversation")
                typeRole: "label"
                typeSize: "small"
                color: MeoTheme.contentOnSurfaceVariant
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2 * root.uiScale

                MeoText {
                    Layout.fillWidth: true
                    text: String(root.digest.title || qsTr("Generated title"))
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    typeRole: "label"
                    typeSize: "medium"
                    color: MeoTheme.contentOnSurface
                }

                MeoText {
                    Layout.fillWidth: true
                    visible: String(root.digest.summary || "").length > 0
                    text: String(root.digest.summary || "")
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                    typeRole: "body"
                    typeSize: "small"
                    color: MeoTheme.contentOnSurfaceVariant
                }

                MeoText {
                    Layout.fillWidth: true
                    visible: String(root.digest.model_id || "").length > 0
                    text: qsTr("Background model: %1").arg(String(root.digest.model_id || ""))
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    typeRole: "label"
                    typeSize: "small"
                    color: MeoTheme.contentOnSurfaceVariant
                }
            }
        }
    }
}
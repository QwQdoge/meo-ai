import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0

Popup {
    id: root
    objectName: "meo.aiResponseDetails"

    property var metadata: ({})
    property real uiScale: MeoTheme.globalScale

    modal: true
    focus: true
    width: Math.min(660 * uiScale, parent ? parent.width - 28 * uiScale : 660 * uiScale)
    height: Math.min(720 * uiScale, parent ? parent.height - 28 * uiScale : 720 * uiScale)
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    function map(value) {
        return value && typeof value === "object" ? value : ({})
    }

    function number(value) {
        return typeof value === "number" && isFinite(value) ? value : null
    }

    function tokenText(value) {
        const n = number(value)
        if (n === null)
            return ""
        if (n >= 1000000)
            return (n / 1000000).toFixed(n >= 10000000 ? 0 : 1) + "M"
        if (n >= 1000)
            return (n / 1000).toFixed(n >= 10000 ? 0 : 1) + "k"
        return String(Math.round(n))
    }

    function durationText(value) {
        const n = number(value)
        if (n === null)
            return ""
        if (n >= 1000)
            return (n / 1000).toFixed(n >= 10000 ? 1 : 2) + " s"
        return Math.round(n) + " ms"
    }

    function safeJson(value) {
        try {
            return JSON.stringify(value || {}, null, 2)
        } catch (error) {
            return qsTr("Metadata could not be formatted.")
        }
    }

    readonly property var usage: map(metadata.usage)
    readonly property var timing: map(metadata.timing)
    readonly property var contextInfo: map(metadata.context)
    readonly property var activity: map(metadata.activity)
    readonly property var reasoning: map(metadata.reasoning)
    readonly property var controlsInfo: map(metadata.controls)
    readonly property var costInfo: map(metadata.cost)
    readonly property var rateLimits: map(metadata.rate_limits)

    background: Rectangle {
        radius: 24 * root.uiScale
        color: MeoTheme.surface
        border.width: Math.max(1, root.uiScale)
        border.color: MeoTheme.outlineVariant
    }

    contentItem: ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20 * root.uiScale
        spacing: 12 * root.uiScale

        RowLayout {
            Layout.fillWidth: true
            spacing: 8 * root.uiScale

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2 * root.uiScale

                MeoText {
                    Layout.fillWidth: true
                    text: qsTr("Response details")
                    typeRole: "title"
                    typeSize: "medium"
                    color: MeoTheme.contentOnSurface
                }

                MeoText {
                    Layout.fillWidth: true
                    text: {
                        const provider = String(root.metadata.provider || "")
                        const model = String(root.metadata.model || "")
                        if (provider.length && model.length)
                            return provider + " · " + model
                        return model.length ? model : (provider.length ? provider : qsTr("Provider metadata"))
                    }
                    typeRole: "body"
                    typeSize: "small"
                    color: MeoTheme.contentOnSurfaceVariant
                    elide: Text.ElideRight
                }
            }

            MeoButton {
                text: qsTr("Close")
                type: "text"
                size: "xs"
                onClicked: root.close()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(1, root.uiScale)
            color: MeoTheme.outlineVariant
            opacity: 0.42
        }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            ColumnLayout {
                width: parent.width
                spacing: 12 * root.uiScale

                Flow {
                    Layout.fillWidth: true
                    spacing: 8 * root.uiScale

                    Rectangle {
                        visible: root.usage.total_tokens !== undefined
                        width: 142 * root.uiScale
                        height: 70 * root.uiScale
                        radius: 16 * root.uiScale
                        color: MeoTheme.surfaceContainerLow
                        Column {
                            anchors.fill: parent
                            anchors.margins: 11 * root.uiScale
                            spacing: 2 * root.uiScale
                            MeoText { text: qsTr("Tokens"); typeRole: "label"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant }
                            MeoText { text: root.tokenText(root.usage.total_tokens); typeRole: "title"; typeSize: "small"; color: MeoTheme.contentOnSurface }
                        }
                    }

                    Rectangle {
                        visible: root.timing.total_ms !== undefined
                        width: 142 * root.uiScale
                        height: 70 * root.uiScale
                        radius: 16 * root.uiScale
                        color: MeoTheme.surfaceContainerLow
                        Column {
                            anchors.fill: parent
                            anchors.margins: 11 * root.uiScale
                            spacing: 2 * root.uiScale
                            MeoText { text: qsTr("Runtime"); typeRole: "label"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant }
                            MeoText { text: root.durationText(root.timing.total_ms); typeRole: "title"; typeSize: "small"; color: MeoTheme.contentOnSurface }
                        }
                    }

                    Rectangle {
                        visible: root.contextInfo.percent_used !== undefined
                        width: 142 * root.uiScale
                        height: 70 * root.uiScale
                        radius: 16 * root.uiScale
                        color: MeoTheme.surfaceContainerLow
                        Column {
                            anchors.fill: parent
                            anchors.margins: 11 * root.uiScale
                            spacing: 2 * root.uiScale
                            MeoText { text: qsTr("Context"); typeRole: "label"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant }
                            MeoText { text: Number(root.contextInfo.percent_used).toFixed(1) + "%"; typeRole: "title"; typeSize: "small"; color: MeoTheme.contentOnSurface }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    visible: Object.keys(root.usage).length > 0
                    spacing: 5 * root.uiScale
                    MeoText { text: qsTr("Usage"); typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurface }
                    MeoText {
                        Layout.fillWidth: true
                        text: [
                            root.usage.input_tokens !== undefined ? qsTr("Input %1").arg(root.tokenText(root.usage.input_tokens)) : "",
                            root.usage.output_tokens !== undefined ? qsTr("Output %1").arg(root.tokenText(root.usage.output_tokens)) : "",
                            root.usage.reasoning_tokens !== undefined ? qsTr("Reasoning %1").arg(root.tokenText(root.usage.reasoning_tokens)) : "",
                            root.usage.cache_read_tokens !== undefined ? qsTr("Cache read %1").arg(root.tokenText(root.usage.cache_read_tokens)) : "",
                            root.usage.cache_write_tokens !== undefined ? qsTr("Cache write %1").arg(root.tokenText(root.usage.cache_write_tokens)) : ""
                        ].filter(function(value) { return value.length > 0 }).join(" · ")
                        wrapMode: Text.Wrap
                        typeRole: "body"
                        typeSize: "small"
                        color: MeoTheme.contentOnSurfaceVariant
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    visible: Object.keys(root.contextInfo).length > 0
                    spacing: 5 * root.uiScale
                    MeoText { text: qsTr("Context"); typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurface }
                    MeoText {
                        Layout.fillWidth: true
                        text: [
                            root.contextInfo.used_tokens !== undefined ? qsTr("Used %1").arg(root.tokenText(root.contextInfo.used_tokens)) : "",
                            root.contextInfo.window_tokens !== undefined ? qsTr("Window %1").arg(root.tokenText(root.contextInfo.window_tokens)) : "",
                            root.contextInfo.remaining_tokens !== undefined ? qsTr("Remaining %1").arg(root.tokenText(root.contextInfo.remaining_tokens)) : "",
                            root.contextInfo.trimmed_messages !== undefined ? qsTr("Trimmed %1 messages").arg(root.contextInfo.trimmed_messages) : "",
                            root.contextInfo.strategy ? String(root.contextInfo.strategy) : ""
                        ].filter(function(value) { return value.length > 0 }).join(" · ")
                        wrapMode: Text.Wrap
                        typeRole: "body"
                        typeSize: "small"
                        color: MeoTheme.contentOnSurfaceVariant
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    visible: Object.keys(root.timing).length > 0
                    spacing: 5 * root.uiScale
                    MeoText { text: qsTr("Timing"); typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurface }
                    MeoText {
                        Layout.fillWidth: true
                        text: [
                            root.timing.first_token_ms !== undefined ? qsTr("First token %1").arg(root.durationText(root.timing.first_token_ms)) : "",
                            root.timing.first_visible_token_ms !== undefined ? qsTr("First visible %1").arg(root.durationText(root.timing.first_visible_token_ms)) : "",
                            root.timing.queue_ms !== undefined ? qsTr("Queue %1").arg(root.durationText(root.timing.queue_ms)) : "",
                            root.timing.tool_ms !== undefined ? qsTr("Tools %1").arg(root.durationText(root.timing.tool_ms)) : "",
                            root.timing.reasoning_ms !== undefined ? qsTr("Reasoning %1").arg(root.durationText(root.timing.reasoning_ms)) : ""
                        ].filter(function(value) { return value.length > 0 }).join(" · ")
                        wrapMode: Text.Wrap
                        typeRole: "body"
                        typeSize: "small"
                        color: MeoTheme.contentOnSurfaceVariant
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    visible: Object.keys(root.activity).length > 0
                    spacing: 5 * root.uiScale
                    MeoText { text: qsTr("Activity"); typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurface }
                    TextArea {
                        Layout.fillWidth: true
                        readOnly: true
                        selectByMouse: true
                        wrapMode: TextEdit.Wrap
                        text: root.safeJson(root.activity)
                        color: MeoTheme.contentOnSurfaceVariant
                        font.family: "monospace"
                        background: null
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    visible: root.reasoning.available === true
                    spacing: 5 * root.uiScale
                    MeoText { text: qsTr("Provider reasoning"); typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurface }
                    MeoText {
                        Layout.fillWidth: true
                        text: String(root.reasoning.text || qsTr("The provider returned reasoning metadata without readable text."))
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        typeRole: "body"
                        typeSize: "small"
                        color: MeoTheme.contentOnSurfaceVariant
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    visible: Object.keys(root.controlsInfo).length > 0 || Object.keys(root.costInfo).length > 0 || Object.keys(root.rateLimits).length > 0
                    spacing: 5 * root.uiScale
                    MeoText { text: qsTr("Request settings & limits"); typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurface }
                    TextArea {
                        Layout.fillWidth: true
                        readOnly: true
                        selectByMouse: true
                        wrapMode: TextEdit.Wrap
                        text: root.safeJson({controls: root.controlsInfo, cost: root.costInfo, rate_limits: root.rateLimits})
                        color: MeoTheme.contentOnSurfaceVariant
                        font.family: "monospace"
                        background: null
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 5 * root.uiScale
                    MeoText { text: qsTr("Raw provider metadata"); typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurface }
                    MeoText {
                        Layout.fillWidth: true
                        text: qsTr("Secret-shaped fields are redacted by AgentService before they reach this view.")
                        wrapMode: Text.Wrap
                        typeRole: "body"
                        typeSize: "small"
                        color: MeoTheme.contentOnSurfaceVariant
                    }
                    TextArea {
                        Layout.fillWidth: true
                        implicitHeight: 190 * root.uiScale
                        readOnly: true
                        selectByMouse: true
                        wrapMode: TextEdit.NoWrap
                        text: root.safeJson(root.metadata.provider_metadata || {})
                        color: MeoTheme.contentOnSurfaceVariant
                        font.family: "monospace"
                        background: Rectangle {
                            radius: 14 * root.uiScale
                            color: MeoTheme.surfaceContainerLow
                        }
                    }
                }
            }
        }
    }
}

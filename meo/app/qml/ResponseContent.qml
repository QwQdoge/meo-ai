import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0

Item {
    id: root
    property var metadata: ({})
    property real uiScale: MeoTheme.globalScale
    property bool showHeading: true
    property var toolEvents: []
    property bool showTechnical: false
    signal closeRequested()

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
    readonly property var searchInfo: map(activity.search)
    readonly property var searchQueries: Array.isArray(searchInfo.queries) ? searchInfo.queries : []
    readonly property var reasoning: map(metadata.reasoning)
    readonly property var controlsInfo: map(metadata.controls)
    readonly property var costInfo: map(metadata.cost)
    readonly property var rateLimits: map(metadata.rate_limits)
    readonly property var citations: Array.isArray(metadata.citations) ? metadata.citations : []
    readonly property bool contextIsRuntimeBudget: contextInfo.status === "runtime_budget"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20 * root.uiScale
        spacing: 12 * root.uiScale

        RowLayout {
            visible: root.showHeading
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
                onClicked: root.closeRequested()
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

                MeoText {
                    Layout.fillWidth: true
                    visible: !root.showHeading
                    text: [root.metadata.provider, root.metadata.model].filter(function(value) { return !!value }).join(" · ")
                    wrapMode: Text.Wrap
                    typeRole: "title"; typeSize: "small"
                    color: MeoTheme.contentOnSurface
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    visible: root.toolEvents.length > 0
                    spacing: 12 * root.uiScale
                    MeoText {
                        text: qsTr("Tool activity")
                        typeRole: "label"; typeSize: "medium"
                        color: MeoTheme.contentOnSurface
                    }
                    Repeater {
                        model: root.toolEvents
                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 10 * root.uiScale
                            MeoIcon {
                                icon: modelData.type === "tool.requested" ? "pending_actions" : "task_alt"
                                size: 20; color: MeoTheme.primary
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2 * root.uiScale
                                MeoText {
                                    Layout.fillWidth: true
                                    text: String(modelData.tool_name || qsTr("Tool"))
                                    wrapMode: Text.Wrap
                                    typeRole: "label"; typeSize: "medium"
                                    color: MeoTheme.contentOnSurface
                                }
                                MeoText {
                                    Layout.fillWidth: true
                                    text: String(modelData.display_text || "")
                                    wrapMode: Text.Wrap
                                    maximumLineCount: 3; elide: Text.ElideRight
                                    typeRole: "body"; typeSize: "small"
                                    color: MeoTheme.contentOnSurfaceVariant
                                }
                            }
                        }
                    }
                }

                Flow {
                    Layout.fillWidth: true
                    spacing: 8 * root.uiScale

                    Rectangle {
                        visible: root.usage.total_tokens !== undefined
                        width: Math.min(142 * root.uiScale, (parent.width - parent.spacing) / 2)
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
                        width: Math.min(142 * root.uiScale, (parent.width - parent.spacing) / 2)
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
                        width: Math.min(142 * root.uiScale, (parent.width - parent.spacing) / 2)
                        height: 70 * root.uiScale
                        radius: 16 * root.uiScale
                        color: MeoTheme.surfaceContainerLow
                        Column {
                            anchors.fill: parent
                            anchors.margins: 11 * root.uiScale
                            spacing: 2 * root.uiScale
                            MeoText {
                                text: root.contextIsRuntimeBudget ? qsTr("Context budget") : qsTr("Context")
                                typeRole: "label"
                                typeSize: "small"
                                color: MeoTheme.contentOnSurfaceVariant
                            }
                            MeoText { text: Number(root.contextInfo.percent_used).toFixed(1) + "%"; typeRole: "title"; typeSize: "small"; color: MeoTheme.contentOnSurface }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    visible: root.metadata.finish_reason !== undefined
                        || root.metadata.response_id !== undefined
                        || root.metadata.request_id_provider !== undefined
                        || root.metadata.service_tier !== undefined
                        || root.metadata.system_fingerprint !== undefined
                    spacing: 5 * root.uiScale
                    MeoText { text: qsTr("Response identity"); typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurface }
                    MeoText {
                        Layout.fillWidth: true
                        text: [
                            root.metadata.finish_reason !== undefined ? qsTr("Finish %1").arg(String(root.metadata.finish_reason)) : "",
                            root.metadata.response_id !== undefined ? qsTr("Response %1").arg(String(root.metadata.response_id)) : "",
                            root.metadata.request_id_provider !== undefined ? qsTr("Request %1").arg(String(root.metadata.request_id_provider)) : "",
                            root.metadata.service_tier !== undefined ? qsTr("Tier %1").arg(String(root.metadata.service_tier)) : "",
                            root.metadata.system_fingerprint !== undefined ? qsTr("Fingerprint %1").arg(String(root.metadata.system_fingerprint)) : ""
                        ].filter(function(value) { return value.length > 0 }).join(" · ")
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        typeRole: "body"
                        typeSize: "small"
                        color: MeoTheme.contentOnSurfaceVariant
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
                            root.usage.cache_write_tokens !== undefined ? qsTr("Cache write %1").arg(root.tokenText(root.usage.cache_write_tokens)) : "",
                            root.usage.audio_input_tokens !== undefined ? qsTr("Audio in %1").arg(root.tokenText(root.usage.audio_input_tokens)) : "",
                            root.usage.audio_output_tokens !== undefined ? qsTr("Audio out %1").arg(root.tokenText(root.usage.audio_output_tokens)) : ""
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
                    MeoText {
                        text: root.contextIsRuntimeBudget ? qsTr("Context budget") : qsTr("Context")
                        typeRole: "label"
                        typeSize: "medium"
                        color: MeoTheme.contentOnSurface
                    }
                    MeoText {
                        Layout.fillWidth: true
                        text: [
                            root.contextInfo.used_tokens !== undefined ? qsTr("Input used %1").arg(root.tokenText(root.contextInfo.used_tokens)) : "",
                            root.contextInfo.window_tokens !== undefined
                                ? (root.contextIsRuntimeBudget ? qsTr("Budget %1").arg(root.tokenText(root.contextInfo.window_tokens)) : qsTr("Window %1").arg(root.tokenText(root.contextInfo.window_tokens)))
                                : "",
                            root.contextInfo.target_tokens !== undefined ? qsTr("Target %1").arg(root.tokenText(root.contextInfo.target_tokens)) : "",
                            root.contextInfo.remaining_tokens !== undefined ? qsTr("Remaining %1").arg(root.tokenText(root.contextInfo.remaining_tokens)) : "",
                            root.contextInfo.max_output_tokens !== undefined ? qsTr("Max output %1").arg(root.tokenText(root.contextInfo.max_output_tokens)) : "",
                            root.contextInfo.trimmed_messages !== undefined ? qsTr("Trimmed %1 messages").arg(root.contextInfo.trimmed_messages) : "",
                            root.contextInfo.trimmed_tokens !== undefined ? qsTr("Trimmed %1 tokens").arg(root.tokenText(root.contextInfo.trimmed_tokens)) : ""
                        ].filter(function(value) { return value.length > 0 }).join(" · ")
                        wrapMode: Text.Wrap
                        typeRole: "body"
                        typeSize: "small"
                        color: MeoTheme.contentOnSurfaceVariant
                    }
                    MeoText {
                        visible: root.contextIsRuntimeBudget
                        Layout.fillWidth: true
                        text: qsTr("This is Meo AI's configured runtime budget, not a provider-certified model context-window size.")
                        wrapMode: Text.Wrap
                        typeRole: "label"
                        typeSize: "small"
                        color: MeoTheme.contentOnSurfaceVariant
                        opacity: 0.72
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
                            root.timing.network_ms !== undefined ? qsTr("Network %1").arg(root.durationText(root.timing.network_ms)) : "",
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
                    visible: root.searchInfo.used === true || root.citations.length > 0
                    spacing: 7 * root.uiScale

                    MeoText {
                        text: qsTr("Search & sources")
                        typeRole: "label"
                        typeSize: "medium"
                        color: MeoTheme.contentOnSurface
                    }

                    MeoText {
                        Layout.fillWidth: true
                        visible: root.searchQueries.length > 0
                        text: qsTr("Queries: %1").arg(root.searchQueries.join(" · "))
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        typeRole: "body"
                        typeSize: "small"
                        color: MeoTheme.contentOnSurfaceVariant
                    }

                    MeoText {
                        Layout.fillWidth: true
                        visible: root.searchInfo.result_count !== undefined
                        text: qsTr("%1 observed search results").arg(root.searchInfo.result_count)
                        typeRole: "label"
                        typeSize: "small"
                        color: MeoTheme.contentOnSurfaceVariant
                    }

                    Repeater {
                        model: root.citations

                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: sourceColumn.implicitHeight + 16 * root.uiScale
                            radius: 14 * root.uiScale
                            color: MeoTheme.surfaceContainerLow

                            ColumnLayout {
                                id: sourceColumn
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 8 * root.uiScale
                                spacing: 2 * root.uiScale

                                MeoText {
                                    Layout.fillWidth: true
                                    text: String(modelData.title || modelData.uri || qsTr("Source"))
                                    textFormat: Text.PlainText
                                    wrapMode: Text.Wrap
                                    typeRole: "label"
                                    typeSize: "medium"
                                    color: MeoTheme.contentOnSurface
                                }

                                TextArea {
                                    Layout.fillWidth: true
                                    visible: String(modelData.uri || "").length > 0
                                    text: String(modelData.uri || "")
                                    textFormat: TextEdit.PlainText
                                    wrapMode: TextEdit.WrapAnywhere
                                    readOnly: true
                                    padding: 0
                                    background: null
                                    font.family: MeoTheme.typefacePlain
                                    font.pixelSize: MeoTheme.typeToken("body", "small", false).size * root.uiScale
                                    color: MeoTheme.primary
                                    selectByMouse: true
                                }

                                MeoText {
                                    Layout.fillWidth: true
                                    visible: String(modelData.provider || "").length > 0
                                    text: String(modelData.provider || "")
                                    typeRole: "label"
                                    typeSize: "small"
                                    color: MeoTheme.contentOnSurfaceVariant
                                    opacity: 0.7
                                }
                            }
                        }
                    }
                }

                MeoButton {
                    visible: Object.keys(root.activity).length > 0 || Object.keys(root.map(root.metadata.provider_metadata)).length > 0
                    text: root.showTechnical ? qsTr("Hide technical metadata") : qsTr("Technical metadata")
                    type: "text"; size: "xs"
                    onClicked: root.showTechnical = !root.showTechnical
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: root.showTechnical && Object.keys(root.activity).length > 0
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
                    visible: root.showTechnical && Object.keys(root.map(root.metadata.provider_metadata)).length > 0
                    spacing: 5 * root.uiScale
                    MeoText { text: qsTr("Raw provider metadata"); typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurface }
                    MeoText {
                        Layout.fillWidth: true
                        text: qsTr("Unknown provider fields are preserved when safe. Secret-shaped fields are redacted by AgentService before this view.")
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

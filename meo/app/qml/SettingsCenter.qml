import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0
import "MeoUiSchema.js" as ProductSchema

Popup {
    id: root
    objectName: "meoAiSettingsCenter"

    property var accountBackend: null
    property real uiScale: MeoTheme.globalScale
    property int currentPage: 0 // Existing runtime page identity, preserved for callers.
    property int currentSection: 0
    property var clientPreferences: null
    readonly property var sections: ProductSchema.configuration.settings.sections
    readonly property var sectionPages: ({general: [0, 3, 7], personalization: [10, 5], models: [1, 2], connectors: [4], devices: [8], privacy: [9], usage: [6], account: [6]})
    function selectSection(index) {
        currentSection = index
        currentPage = sectionPages[sections[index].id][0]
    }

    signal manageMemoryRequested()
    signal openQuickControlsRequested()

    readonly property var pages: [
        { title: qsTr("General"), icon: "tune" },
        { title: qsTr("Providers"), icon: "hub" },
        { title: qsTr("Models"), icon: "deployed_code" },
        { title: qsTr("Agent"), icon: "smart_toy" },
        { title: qsTr("Tools & MCP"), icon: "extension" },
        { title: qsTr("Memory"), icon: "neurology" },
        { title: qsTr("Account & activity"), icon: "account_circle" },
        { title: qsTr("Diagnostics"), icon: "monitor_heart" },
        { title: qsTr("Remote devices"), icon: "devices" },
        { title: qsTr("Data & privacy"), icon: "shield" },
        { title: qsTr("Cloud sync"), icon: "cloud_sync" }
    ]

    readonly property var selectedConnection: {
        if (!root.accountBackend) return ({})
        const items = root.accountBackend.connections || []
        for (let i = 0; i < items.length; ++i) {
            if (String(items[i].id || "") === String(root.accountBackend.selectedConnectionId || ""))
                return items[i]
        }
        return ({})
    }

    readonly property bool independentRoutingReady: {
        const roles = agent.modelRoles || []
        if (!roles.length) return false
        for (let i = 0; i < roles.length; ++i) {
            if (roles[i].runtime_supported !== true) return false
        }
        return true
    }

    function openPage(page) {
        currentPage = Math.max(0, Math.min(root.pages.length - 1, Number(page || 0)))
        for (let i = 0; i < sections.length; ++i) {
            if (sectionPages[sections[i].id].indexOf(currentPage) >= 0) { currentSection = i; break }
        }
        open()
    }

    function roleCurrentModel(role) {
        return String(role.preferred_model_id || role.fallback_model_id || "")
    }

    function roleEligibleModels(role) {
        const models = agent.models || []
        const eligibleIds = role && role.eligible_model_ids ? role.eligible_model_ids : []
        if (!eligibleIds || eligibleIds.length === 0)
            return role && role.capability_available === false ? [] : models

        const allowed = ({})
        for (let i = 0; i < eligibleIds.length; ++i)
            allowed[String(eligibleIds[i])] = true

        const result = []
        for (let i = 0; i < models.length; ++i) {
            if (allowed[String(models[i].model_id || "")] === true)
                result.push(models[i])
        }
        return result
    }

    function providerLabel(connection) {
        if (!connection) return qsTr("AI connection")
        if (connection.provider === "ollama") return qsTr("Ollama")
        if (connection.provider === "openai_compatible") return qsTr("OpenAI-compatible")
        return String(connection.provider || qsTr("Provider"))
    }

    modal: true
    focus: true
    width: Math.min(1100 * uiScale, parent ? parent.width - 32 * uiScale : 1100 * uiScale)
    height: Math.min(780 * uiScale, parent ? parent.height - 32 * uiScale : 780 * uiScale)
    x: parent ? Math.round((parent.width - width) / 2) : 0
    y: parent ? Math.round((parent.height - height) / 2) : 0
    padding: 0
    closePolicy: Popup.CloseOnEscape

    onOpened: {
        if (agent.serviceMode) agent.refreshServiceMetadata()
        if (root.accountBackend) root.accountBackend.refresh()
        if (root.currentPage === 8) cloudPersonalization.refresh()
    }
    onCurrentPageChanged: {
        if (root.currentPage === 8 && root.opened) cloudPersonalization.refresh()
    }

    background: Rectangle {
        radius: 28 * root.uiScale
        color: MeoTheme.surface
        border.width: Math.max(1, root.uiScale)
        border.color: MeoTheme.outlineVariant
    }

    contentItem: RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.preferredWidth: Math.min(248 * root.uiScale, root.width * 0.3)
            Layout.fillHeight: true
            color: MeoTheme.surfaceContainerLow
            radius: 28 * root.uiScale

            Rectangle {
                anchors.right: parent.right
                width: 28 * root.uiScale
                height: parent.height
                color: parent.color
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16 * root.uiScale
                spacing: 8 * root.uiScale

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 4 * root.uiScale
                    Layout.bottomMargin: 12 * root.uiScale
                    spacing: 10 * root.uiScale

                    AiLogo {
                        Layout.preferredWidth: 36 * root.uiScale
                        Layout.preferredHeight: 36 * root.uiScale
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1 * root.uiScale
                        MeoText {
                            text: qsTr("Meo AI settings")
                            typeRole: "title"
                            typeSize: "small"
                            color: MeoTheme.contentOnSurface
                        }
                        MeoText {
                            Layout.fillWidth: true
                            text: qsTr("Local-first controls")
                            typeRole: "label"
                            typeSize: "small"
                            color: MeoTheme.contentOnSurfaceVariant
                            elide: Text.ElideRight
                        }
                    }
                }

                MeoTextField {
                    id: settingsSearch
                    objectName: "meoAiSettingsSearch"
                    Layout.fillWidth: true
                    placeholder: qsTr("Search settings")
                    leadingIcon: "search"
                    size: "s"
                    showClearButton: true
                    Accessible.name: qsTr("Search settings")
                }

                Repeater {
                    model: root.sections
                    delegate: NavigationButton {
                        required property var modelData
                        required property int index
                        objectName: "meoAiSettingsNav-" + index
                        Layout.fillWidth: true
                        visible: {
                            const needle = settingsSearch.text.trim().toLowerCase()
                            if (!needle) return true
                            if (qsTranslate("MeoSettings", modelData.label).toLowerCase().indexOf(needle) >= 0) return true
                            if (modelData.id.toLowerCase().indexOf(needle) >= 0) return true
                            if ((modelData.keywords || []).some(function(term) { return term.toLowerCase().indexOf(needle) >= 0 })) return true
                            const fields = modelData.items || []
                            return fields.some(function(item) {
                                return qsTranslate("MeoSettings", item.label).toLowerCase().indexOf(needle) >= 0
                                    || item.id.replace(/_/g, " ").toLowerCase().indexOf(needle) >= 0
                            })
                        }
                        text: qsTranslate("MeoSettings", modelData.label)
                        icon.name: ({general:"tune",personalization:"neurology",models:"deployed_code",connectors:"extension",devices:"devices",privacy:"shield",usage:"monitor_heart",account:"account_circle"})[modelData.id]
                        type: root.currentSection === index ? "tonal" : "text"
                        size: "s"
                        onClicked: root.selectSection(index)
                    }
                }

                Item { Layout.fillHeight: true }

                MeoText {
                    Layout.fillWidth: true
                    text: agent.serviceMode ? qsTr("AgentService · local") : qsTr("Legacy runtime")
                    typeRole: "label"
                    typeSize: "small"
                    color: MeoTheme.contentOnSurfaceVariant
                    wrapMode: Text.Wrap
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 76 * root.uiScale
                Layout.leftMargin: 24 * root.uiScale
                Layout.rightMargin: 18 * root.uiScale
                spacing: 10 * root.uiScale

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2 * root.uiScale
                    MeoText {
                        text: qsTranslate("MeoSettings", root.sections[root.currentSection].label)
                        typeRole: "title"
                        typeSize: "medium"
                        color: MeoTheme.contentOnSurface
                    }
                    MeoText {
                        Layout.fillWidth: true
                        text: root.currentPage === 1
                            ? qsTr("Provider credentials stay in Meo Account and KWallet; Meo AI receives metadata and brokered access only.")
                            : root.currentPage === 2
                              ? qsTr("Choose models for each workload and see which routing paths are actually active.")
                              : root.currentPage === 4
                                ? qsTr("Manage skills here; MCP server configuration remains owned by the runtime.")
                                : qsTr("Settings are read from the live local runtime, not a mock preferences screen.")
                        typeRole: "body"
                        typeSize: "small"
                        color: MeoTheme.contentOnSurfaceVariant
                        elide: Text.ElideRight
                    }
                }

                MeoIconButton {
                    icon.name: "close"
                    type: "standard"
                    size: "xs"
                    Accessible.name: qsTr("Close settings")
                    onClicked: root.close()
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(1, root.uiScale)
                color: MeoTheme.outlineVariant
                opacity: 0.4
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 24 * root.uiScale
                Layout.topMargin: 8 * root.uiScale
                Repeater {
                    model: root.sectionPages[root.sections[root.currentSection].id]
                    delegate: MeoButton {
                        required property var modelData
                        visible: root.sectionPages[root.sections[root.currentSection].id].length > 1
                        text: modelData < root.pages.length ? root.pages[modelData].title : ""
                        type: root.currentPage === modelData ? "tonal" : "text"
                        size: "xs"
                        onClicked: root.currentPage = modelData
                    }
                }
                Item { Layout.fillWidth: true }
            }

            StackLayout {
                id: settingsStack
                objectName: "meoAiSettingsPages"
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: root.currentPage

                // General
                ScrollView {
                    clip: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: parent.width
                        spacing: 12 * root.uiScale
                        anchors.margins: 22 * root.uiScale

                        Repeater {
                            model: ProductSchema.configuration.settings.sections.filter(function(section) { return section.id === "general" })[0].items
                            delegate: RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.leftMargin: 22 * root.uiScale
                                Layout.rightMargin: 22 * root.uiScale
                                spacing: 20 * root.uiScale
                                MeoText { Layout.fillWidth: true; text: qsTranslate("MeoSettings", modelData.label); typeRole: "body"; typeSize: "medium"; color: MeoTheme.contentOnSurface }
                                Switch {
                                    visible: modelData.kind === "toggle" && ["enter_to_send", "reduce_motion"].indexOf(modelData.id) >= 0
                                    enabled: root.clientPreferences !== null
                                    checked: root.clientPreferences ? (modelData.id === "enter_to_send" ? root.clientPreferences.enterToSend : root.clientPreferences.reduceMotion) : false
                                    Accessible.name: qsTranslate("MeoSettings", modelData.label)
                                    onToggled: {
                                        if (modelData.id === "enter_to_send") root.clientPreferences.enterToSend = checked
                                        else root.clientPreferences.reduceMotion = checked
                                    }
                                }
                                ComboBox {
                                    visible: modelData.id === "theme"
                                    enabled: root.clientPreferences !== null
                                    model: [qsTr("Follow system"), qsTr("Light"), qsTr("Dark")]
                                    currentIndex: root.clientPreferences ? ["system", "light", "dark"].indexOf(root.clientPreferences.themeMode) : 0
                                    Accessible.name: qsTr("Theme")
                                    onActivated: function(index) { root.clientPreferences.themeMode = ["system", "light", "dark"][index] }
                                }
                            }
                        }
                        MeoText { Layout.fillWidth: true; Layout.leftMargin: 22 * root.uiScale; text: qsTr("Saved on this device. Enter sends when enabled; otherwise use Ctrl/⌘ + Enter. Shift + Enter adds a line."); typeRole: "body"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant; wrapMode: Text.Wrap }

                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: generalStatus.implicitHeight + 28 * root.uiScale
                            radius: 20 * root.uiScale
                            color: MeoTheme.surfaceContainerLow
                            RowLayout {
                                id: generalStatus
                                anchors.fill: parent
                                anchors.margins: 14 * root.uiScale
                                spacing: 12 * root.uiScale
                                MeoIcon {
                                    icon: agent.agentState.ready ? "check_circle" : "sync_problem"
                                    size: 30
                                    color: agent.agentState.ready ? MeoTheme.primary : MeoTheme.contentOnSurfaceVariant
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2 * root.uiScale
                                    MeoText {
                                        text: agent.agentState.ready ? qsTr("Local AgentService is ready") : qsTr("Local AgentService is not ready")
                                        typeRole: "title"; typeSize: "small"; color: MeoTheme.contentOnSurface
                                    }
                                    MeoText {
                                        Layout.fillWidth: true
                                        text: agent.metadataStatus || agent.status
                                        typeRole: "body"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant
                                        wrapMode: Text.Wrap
                                    }
                                }
                                MeoButton {
                                    text: qsTr("Refresh")
                                    type: "outlined"; size: "xs"
                                    enabled: agent.serviceMode && !agent.metadataBusy
                                    loading: agent.metadataBusy
                                    onClicked: agent.refreshServiceMetadata()
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: generalCards.implicitHeight + 28 * root.uiScale
                            radius: 20 * root.uiScale
                            color: MeoTheme.surfaceContainerLow
                            ColumnLayout {
                                id: generalCards
                                anchors.fill: parent
                                anchors.margins: 14 * root.uiScale
                                spacing: 10 * root.uiScale
                                MeoText { text: qsTr("Runtime overview"); typeRole: "title"; typeSize: "small"; color: MeoTheme.contentOnSurface }
                                Repeater {
                                    model: [
                                        { title: qsTr("Models"), value: String((agent.models || []).length) },
                                        { title: qsTr("Skills"), value: String((agent.skills || []).length) },
                                        { title: qsTr("MCP servers"), value: String((agent.mcpServers || []).length) },
                                        { title: qsTr("Memory items"), value: String((agent.memories || []).length) }
                                    ]
                                    delegate: RowLayout {
                                        required property var modelData
                                        Layout.fillWidth: true
                                        MeoText { Layout.fillWidth: true; text: modelData.title; typeRole: "body"; typeSize: "medium"; color: MeoTheme.contentOnSurfaceVariant }
                                        MeoText { text: modelData.value; typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurface }
                                    }
                                }
                            }
                        }

                        Item { Layout.fillHeight: true; Layout.minimumHeight: 8 * root.uiScale }
                    }
                }

                // Providers
                ScrollView {
                    clip: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: parent.width
                        spacing: 12 * root.uiScale
                        anchors.margins: 22 * root.uiScale

                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: providerHeader.implicitHeight + 28 * root.uiScale
                            radius: 20 * root.uiScale
                            color: MeoTheme.surfaceContainerLow
                            RowLayout {
                                id: providerHeader
                                anchors.fill: parent
                                anchors.margins: 14 * root.uiScale
                                spacing: 12 * root.uiScale
                                MeoIcon { icon: "key"; size: 28; color: MeoTheme.primary }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2 * root.uiScale
                                    MeoText { text: qsTr("Meo Account provider vault"); typeRole: "title"; typeSize: "small"; color: MeoTheme.contentOnSurface }
                                    MeoText {
                                        Layout.fillWidth: true
                                        text: root.accountBackend ? root.accountBackend.status : qsTr("Account provider bridge is unavailable in this build.")
                                        typeRole: "body"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant; wrapMode: Text.Wrap
                                    }
                                }
                                MeoButton {
                                    text: qsTr("Manage connections")
                                    type: "tonal"; size: "xs"
                                    enabled: root.accountBackend && root.accountBackend.serviceAvailable
                                    onClicked: root.accountBackend.openProviderSettings()
                                }
                            }
                        }

                        MeoText {
                            Layout.fillWidth: true
                            text: qsTr("Available on this device")
                            typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurfaceVariant
                        }

                        Repeater {
                            model: root.accountBackend ? root.accountBackend.connections : []
                            delegate: Rectangle {
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: providerRow.implicitHeight + 28 * root.uiScale
                                radius: 20 * root.uiScale
                                color: String(root.accountBackend.selectedConnectionId || "") === String(modelData.id || "")
                                    ? MeoTheme.secondaryContainer : MeoTheme.surfaceContainerLow
                                RowLayout {
                                    id: providerRow
                                    anchors.fill: parent
                                    anchors.margins: 14 * root.uiScale
                                    spacing: 12 * root.uiScale
                                    MeoIcon {
                                        icon: modelData.provider === "ollama" ? "memory" : "cloud_lock"
                                        size: 30
                                        color: MeoTheme.primary
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 2 * root.uiScale
                                        MeoText {
                                            Layout.fillWidth: true
                                            text: String(modelData.displayName || root.providerLabel(modelData))
                                            typeRole: "title"; typeSize: "small"; color: MeoTheme.contentOnSurface; elide: Text.ElideRight
                                        }
                                        MeoText {
                                            Layout.fillWidth: true
                                            text: root.providerLabel(modelData) + " · " + String(modelData.defaultModel || qsTr("No default model"))
                                            typeRole: "body"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant; elide: Text.ElideRight
                                        }
                                        MeoText {
                                            Layout.fillWidth: true
                                            text: modelData.automaticInferenceEnabled === true
                                                ? qsTr("Automatic inference permission is enabled for this connection")
                                                : qsTr("Prompt-bearing calls still require the Account consent flow")
                                            typeRole: "label"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant; wrapMode: Text.Wrap
                                        }
                                    }
                                    MeoButton {
                                        text: String(root.accountBackend.selectedConnectionId || "") === String(modelData.id || "")
                                            ? qsTr("Selected") : qsTr("Use")
                                        type: String(root.accountBackend.selectedConnectionId || "") === String(modelData.id || "") ? "tonal" : "outlined"
                                        size: "xs"
                                        onClicked: root.accountBackend.selectConnection(String(modelData.id || ""))
                                    }
                                    MeoButton {
                                        text: qsTr("Models")
                                        type: "text"; size: "xs"
                                        enabled: !root.accountBackend.busy
                                        loading: root.accountBackend.busy && String(root.accountBackend.selectedConnectionId || "") === String(modelData.id || "")
                                        onClicked: {
                                            root.accountBackend.selectConnection(String(modelData.id || ""))
                                            root.accountBackend.discoverModels(String(modelData.id || ""))
                                        }
                                    }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            visible: root.accountBackend && root.accountBackend.selectedConnectionId !== ""
                            implicitHeight: providerModelColumn.implicitHeight + 28 * root.uiScale
                            radius: 20 * root.uiScale
                            color: MeoTheme.surfaceContainerLow
                            ColumnLayout {
                                id: providerModelColumn
                                anchors.fill: parent
                                anchors.margins: 14 * root.uiScale
                                spacing: 8 * root.uiScale
                                MeoText { text: qsTr("Preferred provider model"); typeRole: "title"; typeSize: "small"; color: MeoTheme.contentOnSurface }
                                MeoText {
                                    Layout.fillWidth: true
                                    text: qsTr("This preference is stored locally without copying the provider credential. Account-backed inference routing will consume it when that runtime path is enabled.")
                                    typeRole: "body"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant; wrapMode: Text.Wrap
                                }
                                MeoExposedDropdown {
                                    Layout.fillWidth: true
                                    label: qsTr("Model")
                                    model: root.accountBackend ? root.accountBackend.models : []
                                    textRole: "label"
                                    valueRole: "model_id"
                                    currentValue: root.accountBackend ? root.accountBackend.selectedModelId : ""
                                    type: "outlined"
                                    enabled: root.accountBackend && root.accountBackend.models.length > 0 && !root.accountBackend.busy
                                    onSelected: function(index, value) {
                                        if (root.accountBackend && String(value).length) root.accountBackend.selectModel(String(value))
                                    }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            visible: root.accountBackend && root.accountBackend.connections.length === 0
                            implicitHeight: 92 * root.uiScale
                            radius: 20 * root.uiScale
                            color: MeoTheme.surfaceContainerLow
                            RowLayout {
                                anchors.fill: parent; anchors.margins: 14 * root.uiScale; spacing: 12 * root.uiScale
                                MeoIcon { icon: "add_circle"; size: 28; color: MeoTheme.primary }
                                MeoText { Layout.fillWidth: true; text: qsTr("No connection yet. Add Ollama or an OpenAI-compatible provider in Meo Settings; the API key stays in KWallet."); typeRole: "body"; typeSize: "medium"; color: MeoTheme.contentOnSurfaceVariant; wrapMode: Text.Wrap }
                            }
                        }

                        Item { Layout.fillHeight: true; Layout.minimumHeight: 8 * root.uiScale }
                    }
                }

                // Models
                ScrollView {
                    clip: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: parent.width
                        spacing: 12 * root.uiScale
                        anchors.margins: 22 * root.uiScale

                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: routingStatus.implicitHeight + 28 * root.uiScale
                            radius: 20 * root.uiScale
                            color: root.independentRoutingReady ? MeoTheme.secondaryContainer : MeoTheme.surfaceContainerLow
                            RowLayout {
                                id: routingStatus
                                anchors.fill: parent; anchors.margins: 14 * root.uiScale; spacing: 12 * root.uiScale
                                MeoIcon { icon: root.independentRoutingReady ? "route" : "info"; size: 28; color: MeoTheme.primary }
                                MeoText {
                                    Layout.fillWidth: true
                                    text: root.independentRoutingReady
                                        ? qsTr("Independent model routing is active for every role.")
                                        : qsTr("Role choices are saved, but at least one role is still preference-only. The active compatibility runtime may continue using one profile model.")
                                    typeRole: "body"; typeSize: "medium"; color: MeoTheme.contentOnSurfaceVariant; wrapMode: Text.Wrap
                                }
                            }
                        }

                        Repeater {
                            model: agent.modelRoles
                            delegate: Rectangle {
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: modelRoleColumn.implicitHeight + 28 * root.uiScale
                                radius: 20 * root.uiScale
                                color: MeoTheme.surfaceContainerLow
                                ColumnLayout {
                                    id: modelRoleColumn
                                    anchors.fill: parent; anchors.margins: 14 * root.uiScale; spacing: 8 * root.uiScale
                                    RowLayout {
                                        Layout.fillWidth: true
                                        ColumnLayout {
                                            Layout.fillWidth: true; spacing: 2 * root.uiScale
                                            MeoText { text: String(modelData.label || modelData.role_id || ""); typeRole: "title"; typeSize: "small"; color: MeoTheme.contentOnSurface }
                                            MeoText { Layout.fillWidth: true; text: String(modelData.description || ""); typeRole: "body"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant; wrapMode: Text.Wrap }
                                        }
                                        MeoText {
                                            text: modelData.runtime_supported === true ? qsTr("Active") : qsTr("Preference only")
                                            typeRole: "label"; typeSize: "small"
                                            color: modelData.runtime_supported === true ? MeoTheme.primary : MeoTheme.contentOnSurfaceVariant
                                        }
                                    }
                                    MeoExposedDropdown {
                                        Layout.fillWidth: true
                                        label: qsTr("Model")
                                        model: root.roleEligibleModels(modelData)
                                        textRole: "label"
                                        valueRole: "model_id"
                                        currentValue: root.roleCurrentModel(modelData)
                                        type: "outlined"
                                        enabled: root.roleEligibleModels(modelData).length > 0 && !agent.actionBusy
                                        onSelected: function(index, value) {
                                            if (String(value).length) agent.setModelRole(String(modelData.role_id || ""), String(value))
                                        }
                                    }
                                    MeoText {
                                        Layout.fillWidth: true
                                        visible: modelData.capability_available === false
                                        text: qsTr("No compatible model is currently available for this role.")
                                        typeRole: "label"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant
                                        wrapMode: Text.Wrap
                                    }
                                    MeoText {
                                        Layout.fillWidth: true
                                        text: String(modelData.routing_status || "")
                                        visible: text.length > 0
                                        typeRole: "label"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant
                                    }
                                }
                            }
                        }

                        Item { Layout.fillHeight: true; Layout.minimumHeight: 8 * root.uiScale }
                    }
                }

                // Agent
                ScrollView {
                    clip: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: parent.width
                        spacing: 12 * root.uiScale
                        anchors.margins: 22 * root.uiScale

                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: agentIntro.implicitHeight + 28 * root.uiScale
                            radius: 20 * root.uiScale
                            color: MeoTheme.surfaceContainerLow
                            RowLayout {
                                id: agentIntro
                                anchors.fill: parent; anchors.margins: 14 * root.uiScale; spacing: 12 * root.uiScale
                                MeoIcon { icon: "shield"; size: 28; color: MeoTheme.primary }
                                ColumnLayout {
                                    Layout.fillWidth: true; spacing: 2 * root.uiScale
                                    MeoText { text: qsTr("Runtime controls, not authority shortcuts"); typeRole: "title"; typeSize: "small"; color: MeoTheme.contentOnSurface }
                                    MeoText { Layout.fillWidth: true; text: qsTr("Model output never grants system authority. Privileged actions still pass through typed capabilities, Router policy and confirmation."); typeRole: "body"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant; wrapMode: Text.Wrap }
                                }
                                MeoButton { text: qsTr("Quick controls"); type: "tonal"; size: "xs"; onClicked: root.openQuickControlsRequested() }
                            }
                        }

                        Repeater {
                            model: agent.controls
                            delegate: Rectangle {
                                id: controlRow
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: controlColumn.implicitHeight + 28 * root.uiScale
                                radius: 20 * root.uiScale
                                color: MeoTheme.surfaceContainerLow
                                ColumnLayout {
                                    id: controlColumn
                                    anchors.fill: parent; anchors.margins: 14 * root.uiScale; spacing: 7 * root.uiScale
                                    RowLayout {
                                        Layout.fillWidth: true
                                        ColumnLayout {
                                            Layout.fillWidth: true; spacing: 2 * root.uiScale
                                            MeoText { Layout.fillWidth: true; text: String(modelData.label || modelData.control_id || ""); typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurface; elide: Text.ElideRight }
                                            MeoText { visible: String(modelData.description || "").length > 0; Layout.fillWidth: true; text: String(modelData.description || ""); typeRole: "body"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant; wrapMode: Text.Wrap }
                                        }
                                        Switch {
                                            visible: controlRow.modelData.kind === "toggle"
                                            enabled: controlRow.modelData.writable !== false && !agent.actionBusy
                                            checked: controlRow.modelData.value === true
                                            onToggled: agent.setControl(String(controlRow.modelData.control_id || ""), checked)
                                        }
                                    }
                                    ComboBox {
                                        visible: controlRow.modelData.kind === "select"
                                        Layout.fillWidth: true
                                        enabled: controlRow.modelData.writable !== false && !agent.actionBusy
                                        model: controlRow.modelData.options || []
                                        textRole: "label"; valueRole: "value"
                                        currentIndex: {
                                            const options = controlRow.modelData.options || []
                                            for (let i = 0; i < options.length; ++i)
                                                if (String(options[i].value) === String(controlRow.modelData.value)) return i
                                            return -1
                                        }
                                        onActivated: {
                                            const options = controlRow.modelData.options || []
                                            if (currentIndex >= 0 && currentIndex < options.length)
                                                agent.setControl(String(controlRow.modelData.control_id || ""), options[currentIndex].value)
                                        }
                                    }
                                    SpinBox {
                                        visible: controlRow.modelData.kind === "integer"
                                        enabled: controlRow.modelData.writable !== false && !agent.actionBusy
                                        from: controlRow.modelData.minimum !== undefined ? Number(controlRow.modelData.minimum) : 0
                                        to: controlRow.modelData.maximum !== undefined ? Number(controlRow.modelData.maximum) : 1000000
                                        stepSize: controlRow.modelData.step !== undefined ? Number(controlRow.modelData.step) : 1
                                        value: Number(controlRow.modelData.value || 0)
                                        editable: true
                                        onValueModified: agent.setControl(String(controlRow.modelData.control_id || ""), value)
                                    }
                                    MeoText {
                                        visible: controlRow.modelData.kind === "readonly"
                                        Layout.fillWidth: true
                                        text: String(controlRow.modelData.value === undefined ? "" : controlRow.modelData.value)
                                        typeRole: "body"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant; wrapMode: Text.Wrap
                                    }
                                }
                            }
                        }

                        Item { Layout.fillHeight: true; Layout.minimumHeight: 8 * root.uiScale }
                    }
                }

                // Tools & MCP
                ScrollView {
                    clip: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: parent.width
                        spacing: 12 * root.uiScale
                        anchors.margins: 22 * root.uiScale

                        MeoText { text: qsTr("Skills"); typeRole: "title"; typeSize: "small"; color: MeoTheme.contentOnSurface }
                        Repeater {
                            model: agent.skills
                            delegate: Rectangle {
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: 72 * root.uiScale
                                radius: 18 * root.uiScale
                                color: MeoTheme.surfaceContainerLow
                                RowLayout {
                                    anchors.fill: parent; anchors.margins: 12 * root.uiScale; spacing: 10 * root.uiScale
                                    MeoIcon { icon: "extension"; size: 26; color: MeoTheme.primary }
                                    ColumnLayout {
                                        Layout.fillWidth: true; spacing: 2 * root.uiScale
                                        MeoText { Layout.fillWidth: true; text: String(modelData.label || modelData.skill_id || ""); typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurface; elide: Text.ElideRight }
                                        MeoText { Layout.fillWidth: true; text: modelData.override_source ? qsTr("Override: %1").arg(String(modelData.override_source)) : qsTr("Profile skill"); typeRole: "label"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant; elide: Text.ElideRight }
                                    }
                                    Switch {
                                        checked: modelData.enabled === true
                                        enabled: !agent.actionBusy
                                        onToggled: agent.setSkillEnabled(String(modelData.skill_id || ""), checked)
                                    }
                                }
                            }
                        }

                        MeoText { Layout.topMargin: 8 * root.uiScale; text: qsTr("MCP servers"); typeRole: "title"; typeSize: "small"; color: MeoTheme.contentOnSurface }
                        Repeater {
                            model: agent.mcpServers
                            delegate: Rectangle {
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: 68 * root.uiScale
                                radius: 18 * root.uiScale
                                color: MeoTheme.surfaceContainerLow
                                RowLayout {
                                    anchors.fill: parent; anchors.margins: 12 * root.uiScale; spacing: 10 * root.uiScale
                                    MeoIcon { icon: "lan"; size: 26; color: MeoTheme.primary }
                                    ColumnLayout {
                                        Layout.fillWidth: true; spacing: 2 * root.uiScale
                                        MeoText { Layout.fillWidth: true; text: String(modelData.label || modelData.server_id || ""); typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurface; elide: Text.ElideRight }
                                        MeoText { text: modelData.enabled === true ? qsTr("Enabled") : qsTr("Disabled"); typeRole: "label"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant }
                                    }
                                    MeoText { text: qsTr("Runtime managed"); typeRole: "label"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant }
                                }
                            }
                        }

                        MeoText {
                            Layout.fillWidth: true
                            text: qsTr("MCP configuration is shown read-only until AgentService exposes a typed mutation API. Meo AI will not edit hidden runtime files behind the settings UI.")
                            typeRole: "body"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant; wrapMode: Text.Wrap
                        }
                        Item { Layout.fillHeight: true; Layout.minimumHeight: 8 * root.uiScale }
                    }
                }

                // Memory
                ScrollView {
                    clip: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: parent.width
                        spacing: 12 * root.uiScale
                        anchors.margins: 22 * root.uiScale

                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: memoryStatus.implicitHeight + 28 * root.uiScale
                            radius: 20 * root.uiScale
                            color: MeoTheme.surfaceContainerLow
                            RowLayout {
                                id: memoryStatus
                                anchors.fill: parent; anchors.margins: 14 * root.uiScale; spacing: 12 * root.uiScale
                                MeoIcon { icon: "neurology"; size: 30; color: MeoTheme.primary }
                                ColumnLayout {
                                    Layout.fillWidth: true; spacing: 2 * root.uiScale
                                    MeoText { text: agent.memoryState.supported === true ? qsTr("On-device memory") : qsTr("Memory is unavailable in this runtime"); typeRole: "title"; typeSize: "small"; color: MeoTheme.contentOnSurface }
                                    MeoText { Layout.fillWidth: true; text: agent.memoryState.supported === true ? qsTr("%1 stored on this device · automatic recall %2").arg(agent.memories.length).arg(agent.memoryState.enabled === true ? qsTr("on") : qsTr("off")) : qsTr("Switch to AgentService mode to use the managed memory store."); typeRole: "body"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant; wrapMode: Text.Wrap }
                                }
                                Switch {
                                    visible: agent.memoryState.supported === true
                                    checked: agent.memoryState.enabled === true
                                    enabled: !agent.actionBusy
                                    onToggled: agent.setMemoryEnabled(checked)
                                }
                                MeoButton {
                                    text: qsTr("Manage")
                                    type: "tonal"; size: "xs"
                                    enabled: agent.memoryState.supported === true && !agent.actionBusy
                                    onClicked: root.manageMemoryRequested()
                                }
                            }
                        }

                        Repeater {
                            model: agent.memories.slice ? agent.memories.slice(0, 5) : agent.memories
                            delegate: Rectangle {
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: memoryText.implicitHeight + 24 * root.uiScale
                                radius: 18 * root.uiScale
                                color: MeoTheme.surfaceContainerLow
                                MeoText {
                                    id: memoryText
                                    anchors.fill: parent; anchors.margins: 12 * root.uiScale
                                    text: String(modelData.text || "")
                                    typeRole: "body"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant; wrapMode: Text.Wrap
                                }
                            }
                        }
                        Item { Layout.fillHeight: true; Layout.minimumHeight: 8 * root.uiScale }
                    }
                }

                // Account & activity
                ScrollView {
                    clip: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: parent.width
                        spacing: 12 * root.uiScale
                        anchors.margins: 22 * root.uiScale

                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: accountStatus.implicitHeight + 28 * root.uiScale
                            radius: 20 * root.uiScale
                            color: MeoTheme.surfaceContainerLow
                            RowLayout {
                                id: accountStatus
                                anchors.fill: parent; anchors.margins: 14 * root.uiScale; spacing: 12 * root.uiScale
                                MeoIcon { icon: "account_circle"; size: 30; color: MeoTheme.primary }
                                ColumnLayout {
                                    Layout.fillWidth: true; spacing: 2 * root.uiScale
                                    MeoText { text: root.accountBackend && root.accountBackend.signedIn ? qsTr("Meo Account connected") : qsTr("Meo Account not connected"); typeRole: "title"; typeSize: "small"; color: MeoTheme.contentOnSurface }
                                    MeoText { Layout.fillWidth: true; text: qsTr("Meo Account is optional for local AI and device settings. Sign in when you need cloud sync or account connections; credentials remain in the Account broker."); typeRole: "body"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant; wrapMode: Text.Wrap }
                                }
                                MeoButton {
                                    visible: root.accountBackend && !root.accountBackend.signedIn
                                    text: qsTr("Sign in")
                                    type: "filled"
                                    size: "xs"
                                    enabled: root.accountBackend && root.accountBackend.serviceAvailable && !root.accountBackend.busy
                                    loading: root.accountBackend && root.accountBackend.busy
                                    onClicked: root.accountBackend.signIn()
                                }
                                MeoButton { text: qsTr("Account settings"); type: "tonal"; size: "xs"; enabled: root.accountBackend && root.accountBackend.signedIn && !root.accountBackend.busy; onClicked: root.accountBackend.openProviderSettings() }
                            }
                        }

                        ActivityDashboard {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 620 * root.uiScale
                        }
                        Item { Layout.fillHeight: true; Layout.minimumHeight: 8 * root.uiScale }
                    }
                }

                // Diagnostics
                ScrollView {
                    clip: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: parent.width
                        spacing: 10 * root.uiScale
                        anchors.margins: 22 * root.uiScale

                        Repeater {
                            model: [
                                { label: qsTr("Transport"), value: agent.serviceMode ? qsTr("Local AgentService") : qsTr("Legacy local API") },
                                { label: qsTr("AgentService"), value: agent.agentState.ready ? qsTr("Ready") : qsTr("Not ready") },
                                { label: qsTr("Metadata"), value: String(agent.metadataStatus || qsTr("Unknown")) },
                                { label: qsTr("Account broker"), value: root.accountBackend && root.accountBackend.serviceAvailable ? qsTr("Available") : qsTr("Unavailable") },
                                { label: qsTr("Device AI connections"), value: root.accountBackend ? String(root.accountBackend.connections.length) : "0" },
                                { label: qsTr("Model-role routing"), value: root.independentRoutingReady ? qsTr("Active") : qsTr("Partially staged") }
                            ]
                            delegate: Rectangle {
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: 60 * root.uiScale
                                radius: 16 * root.uiScale
                                color: MeoTheme.surfaceContainerLow
                                RowLayout {
                                    anchors.fill: parent; anchors.margins: 12 * root.uiScale; spacing: 12 * root.uiScale
                                    MeoText { Layout.fillWidth: true; text: modelData.label; typeRole: "body"; typeSize: "medium"; color: MeoTheme.contentOnSurfaceVariant }
                                    MeoText { text: modelData.value; typeRole: "label"; typeSize: "medium"; color: MeoTheme.contentOnSurface; horizontalAlignment: Text.AlignRight }
                                }
                            }
                        }

                        MeoButton {
                            Layout.topMargin: 6 * root.uiScale
                            text: qsTr("Refresh all local state")
                            type: "filled"; size: "s"
                            enabled: !agent.metadataBusy
                            onClicked: {
                                agent.refreshServiceMetadata()
                                if (root.accountBackend) root.accountBackend.refresh()
                                usage.refresh()
                            }
                        }
                        MeoText {
                            Layout.fillWidth: true
                            text: qsTr("Diagnostics intentionally show unsupported or staged features instead of pretending they are active.")
                            typeRole: "body"; typeSize: "small"; color: MeoTheme.contentOnSurfaceVariant; wrapMode: Text.Wrap
                        }
                        Item { Layout.fillHeight: true; Layout.minimumHeight: 8 * root.uiScale }
                    }
                }
                // Authenticated remote devices are separate from the local runtime.
                ColumnLayout {
                    Layout.margins: 24 * root.uiScale
                    MeoText { text: qsTr("Remote device service is not connected"); typeRole: "title"; typeSize: "medium"; color: MeoTheme.contentOnSurface }
                    MeoText { Layout.fillWidth: true; text: qsTr("Device registration, revocation and remote Work require the authenticated Meo API. Local runtime readiness does not establish a remote device session."); typeRole: "body"; typeSize: "medium"; color: MeoTheme.contentOnSurfaceVariant; wrapMode: Text.Wrap }
                    Item { Layout.fillHeight: true }
                }
                ColumnLayout {
                    Layout.margins: 24 * root.uiScale
                    MeoText { text: qsTr("Data & privacy"); typeRole: "title"; typeSize: "medium"; color: MeoTheme.contentOnSurface }
                    MeoText { Layout.fillWidth: true; text: qsTr("Manage account data and privacy in Meo Account. Local conversation export and deletion remain available from Chats."); typeRole: "body"; typeSize: "medium"; color: MeoTheme.contentOnSurfaceVariant; wrapMode: Text.Wrap }
                    MeoButton { text: qsTr("Open Meo Account"); type: "tonal"; onClicked: Qt.openUrlExternally("https://account.meoarch.org") }
                    Item { Layout.fillHeight: true }
                }

                // Cloud account-scoped instructions and memory. This is
                // deliberately separate from the device-local AgentService store.
                CloudPersonalizationPage {
                    objectName: "meoAiCloudPersonalizationPage"
                }
            }
        }
    }
}

import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import MeoUI 1.0

Item {
    id: root
    objectName: "meoAiConversationHistory"
    readonly property real uiScale: MeoTheme.globalScale
    readonly property bool searching: searchField.text.trim().length > 0
    property string managementConversationId: ""
    property string managementConversationTitle: ""
    property string exportConversationId: ""

    function beginRename(item) {
        managementConversationId = String(item.id || "")
        managementConversationTitle = String(item.title || qsTr("Untitled chat"))
        renameField.text = managementConversationTitle
        renamePopup.open()
        renameField.forceActiveFocus()
        renameField.selectAll()
    }

    function beginDelete(item) {
        managementConversationId = String(item.id || "")
        managementConversationTitle = String(item.title || qsTr("Untitled chat"))
        deletePopup.open()
    }

    function beginExport(item) {
        exportConversationId = String(item.id || "")
        exportDialog.open()
    }

    onVisibleChanged: {
        if (visible && agent.serviceMode && !agent.actionBusy)
            agent.refreshConversations()
    }

    FileDialog {
        id: exportDialog
        title: qsTr("Export chat as Markdown")
        fileMode: FileDialog.SaveFile
        nameFilters: [qsTr("Markdown files (*.md)"), qsTr("All files (*)")]
        onAccepted: agent.exportConversation(root.exportConversationId, selectedFile)
    }

    Timer {
        id: searchDebounce
        interval: 250
        onTriggered: agent.searchConversations(searchField.text)
    }

    Timer {
        id: newChatRefresh
        interval: 100
        repeat: true
        onTriggered: {
            if (agent.busy || agent.actionBusy)
                return
            stop()
            agent.refreshConversations()
            if (root.searching)
                searchDebounce.restart()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10 * root.uiScale

        RowLayout {
            Layout.fillWidth: true
            spacing: 8 * root.uiScale

            MeoButton {
                text: qsTr("New chat")
                icon.name: "add"
                type: "tonal"
                size: "s"
                enabled: agent.serviceMode && !agent.busy && agent.options.length === 0
                onClicked: {
                    agent.newChat()
                    newChatRefresh.restart()
                }
            }

            TextField {
                id: searchField
                objectName: "meoAiConversationSearch"
                Layout.fillWidth: true
                placeholderText: qsTr("Search all chats")
                selectByMouse: true
                color: MeoTheme.contentOnSurface
                onTextChanged: {
                    if (text.trim().length === 0) {
                        searchDebounce.stop()
                        agent.searchConversations("")
                    } else {
                        searchDebounce.restart()
                    }
                }
                background: Rectangle {
                    radius: 15 * root.uiScale
                    color: MeoTheme.surfaceContainerLowest
                    border.width: Math.max(1, root.uiScale)
                    border.color: searchField.activeFocus ? MeoTheme.primary : MeoTheme.outlineVariant
                }
            }

            MeoIconButton {
                icon.name: "refresh"
                type: "standard"
                size: "xs"
                enabled: agent.serviceMode && !agent.actionBusy
                Accessible.name: qsTr("Refresh chats")
                ToolTip.visible: hovered
                ToolTip.text: Accessible.name
                onClicked: {
                    agent.refreshConversations()
                    if (root.searching)
                        searchDebounce.restart()
                }
            }
        }

        MeoText {
            Layout.fillWidth: true
            visible: !root.searching && agent.conversations.length === 0 && !agent.actionBusy
            text: qsTr("No saved Meo AI conversations yet.")
            typeRole: "body"
            typeSize: "small"
            color: MeoTheme.contentOnSurfaceVariant
            wrapMode: Text.Wrap
        }

        MeoText {
            Layout.fillWidth: true
            visible: root.searching && agent.conversationSearchBusy
            text: qsTr("Searching message history…")
            typeRole: "label"
            typeSize: "small"
            color: MeoTheme.contentOnSurfaceVariant
        }

        MeoText {
            Layout.fillWidth: true
            visible: root.searching && !agent.conversationSearchBusy && agent.conversationSearchResults.length === 0
            text: qsTr("No chats matched this search.")
            typeRole: "body"
            typeSize: "small"
            color: MeoTheme.contentOnSurfaceVariant
            wrapMode: Text.Wrap
        }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: availableWidth

            ColumnLayout {
                width: parent.width
                spacing: 8 * root.uiScale

                Repeater {
                    model: root.searching ? agent.conversationSearchResults : agent.conversations

                    delegate: Rectangle {
                        id: conversationCard
                        required property var modelData
                        readonly property bool currentConversation: String(modelData.id || "") === agent.conversationId
                        Layout.fillWidth: true
                        implicitHeight: conversationRow.implicitHeight + 24 * root.uiScale
                        radius: 18 * root.uiScale
                        color: currentConversation ? MeoTheme.surfaceContainer : MeoTheme.surfaceContainerLowest
                        border.width: currentConversation ? Math.max(1, root.uiScale) : 0
                        border.color: MeoTheme.primary

                        RowLayout {
                            id: conversationRow
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 12 * root.uiScale
                            spacing: 8 * root.uiScale

                            MeoIcon {
                                icon: "chat_bubble"
                                size: 24
                                color: MeoTheme.primary
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 3 * root.uiScale

                                MeoText {
                                    Layout.fillWidth: true
                                    text: String(modelData.title || qsTr("Untitled chat"))
                                    typeRole: "title"
                                    typeSize: "small"
                                    color: MeoTheme.contentOnSurface
                                    elide: Text.ElideRight
                                }

                                MeoText {
                                    Layout.fillWidth: true
                                    visible: String(modelData.excerpt || modelData.summary || "").length > 0
                                    text: String(modelData.excerpt || modelData.summary || "")
                                    typeRole: "body"
                                    typeSize: "small"
                                    color: MeoTheme.contentOnSurfaceVariant
                                    maximumLineCount: 2
                                    elide: Text.ElideRight
                                    wrapMode: Text.Wrap
                                }

                                MeoText {
                                    Layout.fillWidth: true
                                    visible: modelData.message_count !== undefined
                                    text: qsTr("%1 messages").arg(Number(modelData.message_count || 0))
                                    typeRole: "label"
                                    typeSize: "small"
                                    color: MeoTheme.contentOnSurfaceVariant
                                    opacity: 0.72
                                }
                            }

                            MeoButton {
                                text: conversationCard.currentConversation ? qsTr("Current") : qsTr("Open")
                                type: conversationCard.currentConversation ? "tonal" : "text"
                                size: "xs"
                                enabled: !conversationCard.currentConversation
                                    && !agent.busy
                                    && !agent.actionBusy
                                    && agent.options.length === 0
                                onClicked: agent.resumeConversation(String(modelData.id || ""))
                            }

                            MeoButton {
                                text: qsTr("Export")
                                type: "text"
                                size: "xs"
                                enabled: !agent.busy && !agent.actionBusy
                                onClicked: root.beginExport(modelData)
                            }

                            MeoIconButton {
                                icon.name: "edit"
                                type: "standard"
                                size: "xs"
                                enabled: !agent.busy && !agent.actionBusy
                                Accessible.name: qsTr("Rename chat")
                                ToolTip.visible: hovered
                                ToolTip.text: Accessible.name
                                onClicked: root.beginRename(modelData)
                            }

                            MeoIconButton {
                                icon.name: "delete"
                                type: "standard"
                                size: "xs"
                                enabled: !agent.busy
                                    && !agent.actionBusy
                                    && agent.options.length === 0
                                    && (!conversationCard.currentConversation || agent.pendingResources.length === 0)
                                Accessible.name: qsTr("Delete chat")
                                ToolTip.visible: hovered
                                ToolTip.text: conversationCard.currentConversation && agent.pendingResources.length > 0
                                    ? qsTr("Remove pending attachments before deleting this chat")
                                    : Accessible.name
                                onClicked: root.beginDelete(modelData)
                            }
                        }
                    }
                }

                Item {
                    Layout.fillHeight: true
                    Layout.minimumHeight: 4 * root.uiScale
                }
            }
        }

        MeoText {
            Layout.fillWidth: true
            text: root.searching
                ? qsTr("Search checks saved chat titles and visible message text on this device.")
                : qsTr("Switching chats restores saved visible messages only. It never replays old model or tool actions.")
            typeRole: "label"
            typeSize: "small"
            color: MeoTheme.contentOnSurfaceVariant
            opacity: 0.72
            wrapMode: Text.Wrap
        }
    }

    Popup {
        id: renamePopup
        parent: Overlay.overlay
        modal: true
        focus: true
        width: Math.min(420 * root.uiScale, parent ? parent.width - 32 * root.uiScale : 420 * root.uiScale)
        padding: 0
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            radius: 24 * root.uiScale
            color: MeoTheme.surface
            border.width: Math.max(1, root.uiScale)
            border.color: MeoTheme.outlineVariant
        }

        contentItem: ColumnLayout {
            spacing: 14 * root.uiScale
            anchors.margins: 20 * root.uiScale

            MeoText {
                Layout.fillWidth: true
                text: qsTr("Rename chat")
                typeRole: "title"
                typeSize: "medium"
                color: MeoTheme.contentOnSurface
            }

            TextField {
                id: renameField
                objectName: "meoAiConversationRenameField"
                Layout.fillWidth: true
                placeholderText: qsTr("Chat title")
                selectByMouse: true
                maximumLength: 240
                color: MeoTheme.contentOnSurface
                background: Rectangle {
                    radius: 14 * root.uiScale
                    color: MeoTheme.surfaceContainerLow
                    border.width: Math.max(1, root.uiScale)
                    border.color: renameField.activeFocus ? MeoTheme.primary : MeoTheme.outlineVariant
                }
                Keys.onReturnPressed: {
                    if (text.trim().length > 0) {
                        agent.renameConversation(root.managementConversationId, text)
                        renamePopup.close()
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                MeoButton {
                    text: qsTr("Cancel")
                    type: "text"
                    size: "s"
                    onClicked: renamePopup.close()
                }
                MeoButton {
                    text: qsTr("Save")
                    type: "filled"
                    size: "s"
                    enabled: renameField.text.trim().length > 0 && !agent.actionBusy
                    onClicked: {
                        agent.renameConversation(root.managementConversationId, renameField.text)
                        renamePopup.close()
                    }
                }
            }
        }
    }

    Popup {
        id: deletePopup
        parent: Overlay.overlay
        modal: true
        focus: true
        width: Math.min(440 * root.uiScale, parent ? parent.width - 32 * root.uiScale : 440 * root.uiScale)
        padding: 0
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            radius: 24 * root.uiScale
            color: MeoTheme.surface
            border.width: Math.max(1, root.uiScale)
            border.color: MeoTheme.outlineVariant
        }

        contentItem: ColumnLayout {
            spacing: 12 * root.uiScale
            anchors.margins: 20 * root.uiScale

            MeoText {
                Layout.fillWidth: true
                text: qsTr("Delete chat?")
                typeRole: "title"
                typeSize: "medium"
                color: MeoTheme.contentOnSurface
            }

            MeoText {
                Layout.fillWidth: true
                text: qsTr("“%1” will be permanently removed from this device. Conversation-scoped attachments are deleted with it.").arg(root.managementConversationTitle)
                typeRole: "body"
                typeSize: "medium"
                color: MeoTheme.contentOnSurfaceVariant
                wrapMode: Text.Wrap
            }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                MeoButton {
                    text: qsTr("Cancel")
                    type: "text"
                    size: "s"
                    onClicked: deletePopup.close()
                }
                MeoButton {
                    text: qsTr("Delete")
                    type: "filled"
                    size: "s"
                    enabled: !agent.busy && !agent.actionBusy
                    onClicked: {
                        agent.deleteConversation(root.managementConversationId)
                        deletePopup.close()
                    }
                }
            }
        }
    }
}
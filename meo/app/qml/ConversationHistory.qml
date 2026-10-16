import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0

Item {
    id: root
    objectName: "meoAiConversationHistory"
    readonly property real uiScale: MeoTheme.globalScale

    function matches(item) {
        const query = searchField.text.trim().toLowerCase()
        if (!query.length)
            return true
        const title = String(item.title || "").toLowerCase()
        const summary = String(item.summary || "").toLowerCase()
        return title.indexOf(query) >= 0 || summary.indexOf(query) >= 0
    }

    onVisibleChanged: {
        if (visible && agent.serviceMode && !agent.actionBusy)
            agent.refreshConversations()
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10 * root.uiScale

        RowLayout {
            Layout.fillWidth: true
            spacing: 8 * root.uiScale

            TextField {
                id: searchField
                objectName: "meoAiConversationSearch"
                Layout.fillWidth: true
                placeholderText: qsTr("Search chats")
                selectByMouse: true
                color: MeoTheme.contentOnSurface
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
                onClicked: agent.refreshConversations()
            }
        }

        MeoText {
            Layout.fillWidth: true
            visible: agent.conversations.length === 0 && !agent.actionBusy
            text: qsTr("No saved Meo AI conversations yet.")
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
                    model: agent.conversations

                    delegate: Rectangle {
                        id: conversationCard
                        required property var modelData
                        readonly property bool currentConversation: String(modelData.id || "") === agent.conversationId
                        visible: root.matches(modelData)
                        Layout.fillWidth: true
                        implicitHeight: visible ? conversationRow.implicitHeight + 24 * root.uiScale : 0
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
                            spacing: 10 * root.uiScale

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
                                    visible: String(modelData.summary || "").length > 0
                                    text: String(modelData.summary || "")
                                    typeRole: "body"
                                    typeSize: "small"
                                    color: MeoTheme.contentOnSurfaceVariant
                                    maximumLineCount: 2
                                    elide: Text.ElideRight
                                    wrapMode: Text.Wrap
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
            text: qsTr("Switching chats restores saved visible messages only. It never replays old model or tool actions.")
            typeRole: "label"
            typeSize: "small"
            color: MeoTheme.contentOnSurfaceVariant
            opacity: 0.72
            wrapMode: Text.Wrap
        }
    }
}

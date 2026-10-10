import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0

Popup {
    id: root
    objectName: "meo.aiMemory"

    property var memoryState: ({})
    property var memories: []
    property bool actionBusy: false
    property real uiScale: MeoTheme.globalScale
    signal enabledRequested(bool enabled)
    signal createRequested(string text, bool pinned)
    signal updateRequested(string memoryId, string text, bool pinned)
    signal deleteRequested(string memoryId)

    modal: true
    focus: true
    width: Math.min(700 * uiScale, parent ? parent.width - 28 * uiScale : 700 * uiScale)
    height: Math.min(720 * uiScale, parent ? parent.height - 28 * uiScale : 720 * uiScale)
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    function matches(item) {
        const wanted = searchField.text.trim().toLowerCase()
        if (!wanted.length)
            return true
        return String(item.text || "").toLowerCase().indexOf(wanted) >= 0
            || String(item.source || "").toLowerCase().indexOf(wanted) >= 0
            || String(item.scope || "").toLowerCase().indexOf(wanted) >= 0
    }

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
            spacing: 10 * root.uiScale

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2 * root.uiScale

                MeoText {
                    Layout.fillWidth: true
                    text: qsTr("Memory")
                    typeRole: "title"
                    typeSize: "medium"
                    color: MeoTheme.contentOnSurface
                }

                MeoText {
                    Layout.fillWidth: true
                    text: root.memoryState.supported === true
                        ? qsTr("Review what Meo AI can recall about you and your work.")
                        : qsTr("The active memory provider does not expose an inspectable store.")
                    typeRole: "body"
                    typeSize: "small"
                    color: MeoTheme.contentOnSurfaceVariant
                    wrapMode: Text.Wrap
                }
            }

            Switch {
                visible: root.memoryState.supported === true
                enabled: !root.actionBusy
                checked: root.memoryState.enabled === true
                onToggled: root.enabledRequested(checked)
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

        ColumnLayout {
            Layout.fillWidth: true
            visible: root.memoryState.supported === true
            spacing: 8 * root.uiScale

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: newMemoryColumn.implicitHeight + 24 * root.uiScale
                radius: 18 * root.uiScale
                color: MeoTheme.surfaceContainerLow

                ColumnLayout {
                    id: newMemoryColumn
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 12 * root.uiScale
                    spacing: 8 * root.uiScale

                    MeoText {
                        Layout.fillWidth: true
                        text: qsTr("Add memory")
                        typeRole: "label"
                        typeSize: "medium"
                        color: MeoTheme.contentOnSurface
                    }

                    TextArea {
                        id: newMemoryText
                        Layout.fillWidth: true
                        Layout.preferredHeight: 62 * root.uiScale
                        placeholderText: qsTr("Something useful to remember…")
                        wrapMode: TextEdit.Wrap
                        selectByMouse: true
                        color: MeoTheme.contentOnSurface
                        font.family: MeoTheme.typefacePlain
                        background: Rectangle {
                            radius: 14 * root.uiScale
                            color: MeoTheme.surfaceContainerLowest
                            border.width: Math.max(1, root.uiScale)
                            border.color: MeoTheme.outlineVariant
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8 * root.uiScale

                        CheckBox {
                            id: newMemoryPinned
                            text: qsTr("Pin")
                            enabled: !root.actionBusy
                        }

                        Item { Layout.fillWidth: true }

                        MeoButton {
                            text: qsTr("Save")
                            type: "filled"
                            size: "xs"
                            enabled: !root.actionBusy && newMemoryText.text.trim().length > 0
                            onClicked: {
                                root.createRequested(newMemoryText.text.trim(), newMemoryPinned.checked)
                                newMemoryText.text = ""
                                newMemoryPinned.checked = false
                            }
                        }
                    }
                }
            }

            TextField {
                id: searchField
                Layout.fillWidth: true
                placeholderText: qsTr("Search memory")
                selectByMouse: true
            }
        }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.memoryState.supported === true
            clip: true

            Column {
                width: parent.width
                spacing: 8 * root.uiScale

                Repeater {
                    model: root.memories

                    delegate: Rectangle {
                        id: memoryCard
                        required property var modelData
                        readonly property bool matchesSearch: root.matches(modelData)
                        width: parent.width
                        implicitHeight: matchesSearch ? memoryColumn.implicitHeight + 24 * root.uiScale : 0
                        visible: matchesSearch
                        radius: 18 * root.uiScale
                        color: MeoTheme.surfaceContainerLow

                        ColumnLayout {
                            id: memoryColumn
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 12 * root.uiScale
                            spacing: 7 * root.uiScale

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8 * root.uiScale

                                MeoText {
                                    Layout.fillWidth: true
                                    text: [
                                        String(memoryCard.modelData.scope || qsTr("Memory")),
                                        String(memoryCard.modelData.sync_state || "local")
                                    ].join(" · ")
                                    typeRole: "label"
                                    typeSize: "small"
                                    color: MeoTheme.contentOnSurfaceVariant
                                    elide: Text.ElideRight
                                }

                                CheckBox {
                                    id: pinnedBox
                                    text: qsTr("Pinned")
                                    checked: memoryCard.modelData.pinned === true
                                    enabled: !root.actionBusy
                                }
                            }

                            TextArea {
                                id: memoryText
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.max(64 * root.uiScale, implicitHeight)
                                text: String(memoryCard.modelData.text || "")
                                wrapMode: TextEdit.Wrap
                                selectByMouse: true
                                color: MeoTheme.contentOnSurface
                                font.family: MeoTheme.typefacePlain
                                background: Rectangle {
                                    radius: 12 * root.uiScale
                                    color: MeoTheme.surfaceContainerLowest
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8 * root.uiScale

                                MeoText {
                                    Layout.fillWidth: true
                                    text: String(memoryCard.modelData.source || "")
                                    typeRole: "label"
                                    typeSize: "small"
                                    color: MeoTheme.contentOnSurfaceVariant
                                    opacity: 0.7
                                    elide: Text.ElideRight
                                }

                                MeoButton {
                                    text: qsTr("Delete")
                                    type: "text"
                                    size: "xs"
                                    enabled: !root.actionBusy
                                    onClicked: root.deleteRequested(String(memoryCard.modelData.memory_id || ""))
                                }

                                MeoButton {
                                    text: qsTr("Save")
                                    type: "tonal"
                                    size: "xs"
                                    enabled: !root.actionBusy && memoryText.text.trim().length > 0
                                    onClicked: root.updateRequested(
                                        String(memoryCard.modelData.memory_id || ""),
                                        memoryText.text.trim(),
                                        pinnedBox.checked)
                                }
                            }
                        }
                    }
                }

                MeoText {
                    visible: root.memories.length === 0
                    width: parent.width
                    text: qsTr("No saved memories yet.")
                    typeRole: "body"
                    typeSize: "medium"
                    color: MeoTheme.contentOnSurfaceVariant
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    topPadding: 28 * root.uiScale
                }
            }
        }

        MeoText {
            visible: root.memoryState.supported !== true
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: qsTr("Memory remains local and unavailable in this view until the selected provider exposes an authoritative store.")
            typeRole: "body"
            typeSize: "medium"
            color: MeoTheme.contentOnSurfaceVariant
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.Wrap
        }

        MeoText {
            visible: root.memoryState.supported === true
            Layout.fillWidth: true
            text: qsTr("Deleting here removes the item from the owning memory store. Model output alone cannot delete memory.")
            typeRole: "label"
            typeSize: "small"
            color: MeoTheme.contentOnSurfaceVariant
            opacity: 0.72
            wrapMode: Text.Wrap
        }
    }
}

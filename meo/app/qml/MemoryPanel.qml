import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0

Popup {
    id: root
    objectName: "meo.aiMemoryPanel"

    property var memoryState: ({})
    property var memories: []
    property bool busy: false
    property real uiScale: MeoTheme.globalScale
    property string editingId: ""
    property string editingText: ""
    property bool editingPinned: false

    signal refreshRequested(string query)
    signal enabledChangeRequested(bool enabled)
    signal createRequested(string text, bool pinned)
    signal updateRequested(string memoryId, string text, bool pinned)
    signal deleteRequested(string memoryId)

    modal: true
    focus: true
    width: Math.min(700 * uiScale, parent ? parent.width - 28 * uiScale : 700 * uiScale)
    height: Math.min(720 * uiScale, parent ? parent.height - 28 * uiScale : 720 * uiScale)
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    function memoryMatches(item) {
        const wanted = searchField.text.trim().toLowerCase()
        if (!wanted.length)
            return true
        return String(item.text || "").toLowerCase().indexOf(wanted) >= 0
            || String(item.source || "").toLowerCase().indexOf(wanted) >= 0
            || String(item.scope || "").toLowerCase().indexOf(wanted) >= 0
    }

    function matchingMemoryCount() {
        let count = 0
        for (let i = 0; i < root.memories.length; ++i) {
            if (memoryMatches(root.memories[i]))
                ++count
        }
        return count
    }

    onOpened: refreshRequested(searchField.text)

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
                    text: root.memoryState.supported === false
                        ? qsTr("The selected memory provider cannot be managed here.")
                        : qsTr("Inspect and control durable memories used across chats.")
                    typeRole: "body"
                    typeSize: "small"
                    color: MeoTheme.contentOnSurfaceVariant
                    wrapMode: Text.Wrap
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
            opacity: 0.38
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10 * root.uiScale

            Switch {
                id: enabledSwitch
                enabled: root.memoryState.supported !== false && !root.busy
                checked: root.memoryState.enabled === true
                onToggled: root.enabledChangeRequested(checked)
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0

                MeoText {
                    Layout.fillWidth: true
                    text: qsTr("Long-term memory")
                    typeRole: "label"
                    typeSize: "medium"
                    color: MeoTheme.contentOnSurface
                }

                MeoText {
                    Layout.fillWidth: true
                    text: enabledSwitch.checked
                        ? qsTr("Automatic recall is enabled.")
                        : qsTr("Saved memories stay visible, but automatic recall is disabled.")
                    typeRole: "body"
                    typeSize: "small"
                    color: MeoTheme.contentOnSurfaceVariant
                    wrapMode: Text.Wrap
                }
            }

            MeoText {
                visible: root.busy
                text: qsTr("Working…")
                typeRole: "label"
                typeSize: "small"
                color: MeoTheme.primary
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8 * root.uiScale

            TextField {
                id: searchField
                Layout.fillWidth: true
                placeholderText: qsTr("Search memories")
                enabled: !root.busy && root.memoryState.supported !== false
                selectByMouse: true
                onAccepted: root.refreshRequested(text)
            }

            MeoButton {
                text: qsTr("Refresh")
                type: "tonal"
                size: "s"
                enabled: !root.busy && root.memoryState.supported !== false
                onClicked: root.refreshRequested(searchField.text)
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: addColumn.implicitHeight + 20 * root.uiScale
            radius: 18 * root.uiScale
            color: MeoTheme.surfaceContainerLow
            visible: root.memoryState.supported !== false

            ColumnLayout {
                id: addColumn
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 10 * root.uiScale
                spacing: 7 * root.uiScale

                TextArea {
                    id: newMemory
                    Layout.fillWidth: true
                    Layout.preferredHeight: 62 * root.uiScale
                    placeholderText: qsTr("Add something Meo AI should remember")
                    wrapMode: TextEdit.Wrap
                    selectByMouse: true
                    enabled: !root.busy
                }

                RowLayout {
                    Layout.fillWidth: true
                    CheckBox {
                        id: pinNew
                        text: qsTr("Pin")
                        enabled: !root.busy
                    }
                    Item { Layout.fillWidth: true }
                    MeoButton {
                        text: qsTr("Add memory")
                        type: "filled"
                        size: "s"
                        enabled: !root.busy && newMemory.text.trim().length > 0
                        onClicked: {
                            root.createRequested(newMemory.text, pinNew.checked)
                            newMemory.text = ""
                            pinNew.checked = false
                        }
                    }
                }
            }
        }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            Column {
                width: parent.width
                spacing: 8 * root.uiScale

                MeoText {
                    visible: !root.busy && root.memoryState.supported !== false && root.matchingMemoryCount() === 0
                    width: parent.width
                    text: searchField.text.trim().length
                        ? qsTr("No memories match this search.")
                        : qsTr("No managed memories yet.")
                    typeRole: "body"
                    typeSize: "small"
                    color: MeoTheme.contentOnSurfaceVariant
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    topPadding: 18 * root.uiScale
                    bottomPadding: 18 * root.uiScale
                }

                Repeater {
                    model: root.memories

                    delegate: Rectangle {
                        required property var modelData
                        readonly property bool matchesSearch: root.memoryMatches(modelData)
                        width: parent.width
                        visible: matchesSearch
                        implicitHeight: matchesSearch ? memoryColumn.implicitHeight + 22 * root.uiScale : 0
                        radius: 18 * root.uiScale
                        color: MeoTheme.surfaceContainerLow

                        ColumnLayout {
                            id: memoryColumn
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 11 * root.uiScale
                            spacing: 6 * root.uiScale

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8 * root.uiScale

                                MeoText {
                                    Layout.fillWidth: true
                                    text: modelData.pinned ? qsTr("Pinned memory") : qsTr("Memory")
                                    typeRole: "label"
                                    typeSize: "small"
                                    color: modelData.pinned ? MeoTheme.primary : MeoTheme.contentOnSurfaceVariant
                                }

                                MeoText {
                                    text: String(modelData.sync_state || "local")
                                    typeRole: "label"
                                    typeSize: "small"
                                    color: MeoTheme.contentOnSurfaceVariant
                                    opacity: 0.64
                                }
                            }

                            MeoText {
                                Layout.fillWidth: true
                                text: String(modelData.text || "")
                                textFormat: Text.PlainText
                                wrapMode: Text.Wrap
                                typeRole: "body"
                                typeSize: "medium"
                                color: MeoTheme.contentOnSurface
                            }

                            MeoText {
                                Layout.fillWidth: true
                                text: String(modelData.source || "")
                                visible: text.length > 0
                                typeRole: "label"
                                typeSize: "small"
                                color: MeoTheme.contentOnSurfaceVariant
                                opacity: 0.64
                                elide: Text.ElideRight
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 4 * root.uiScale

                                MeoButton {
                                    text: modelData.pinned ? qsTr("Unpin") : qsTr("Pin")
                                    type: "text"
                                    size: "xs"
                                    enabled: !root.busy
                                    onClicked: root.updateRequested(
                                        String(modelData.memory_id || ""),
                                        String(modelData.text || ""),
                                        !modelData.pinned)
                                }

                                MeoButton {
                                    text: qsTr("Edit")
                                    type: "text"
                                    size: "xs"
                                    enabled: !root.busy
                                    onClicked: {
                                        root.editingId = String(modelData.memory_id || "")
                                        root.editingText = String(modelData.text || "")
                                        root.editingPinned = modelData.pinned === true
                                    }
                                }

                                Item { Layout.fillWidth: true }

                                MeoButton {
                                    text: qsTr("Delete")
                                    type: "text"
                                    size: "xs"
                                    enabled: !root.busy
                                    onClicked: root.deleteRequested(String(modelData.memory_id || ""))
                                }
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            visible: root.editingId.length > 0
            Layout.fillWidth: true
            implicitHeight: editColumn.implicitHeight + 18 * root.uiScale
            radius: 18 * root.uiScale
            color: MeoTheme.surfaceContainer

            ColumnLayout {
                id: editColumn
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 9 * root.uiScale
                spacing: 7 * root.uiScale

                MeoText {
                    Layout.fillWidth: true
                    text: qsTr("Edit memory")
                    typeRole: "label"
                    typeSize: "medium"
                    color: MeoTheme.contentOnSurface
                }

                TextArea {
                    id: editTextArea
                    Layout.fillWidth: true
                    Layout.preferredHeight: 70 * root.uiScale
                    text: root.editingText
                    wrapMode: TextEdit.Wrap
                    selectByMouse: true
                    enabled: !root.busy
                }

                RowLayout {
                    Layout.fillWidth: true
                    Item { Layout.fillWidth: true }
                    MeoButton {
                        text: qsTr("Cancel")
                        type: "text"
                        size: "xs"
                        onClicked: {
                            root.editingId = ""
                            root.editingText = ""
                            root.editingPinned = false
                        }
                    }
                    MeoButton {
                        text: qsTr("Save")
                        type: "filled"
                        size: "xs"
                        enabled: !root.busy && editTextArea.text.trim().length > 0
                        onClicked: {
                            root.updateRequested(root.editingId, editTextArea.text, root.editingPinned)
                            root.editingId = ""
                            root.editingText = ""
                            root.editingPinned = false
                        }
                    }
                }
            }
        }
    }
}

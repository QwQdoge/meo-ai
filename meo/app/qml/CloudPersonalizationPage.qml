import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0

ScrollView {
    id: root
    clip: true
    contentWidth: availableWidth
    property real uiScale: MeoTheme.globalScale
    property string editingId: ""
    property int editingVersion: 0
    property string deletingId: ""
    // Do not replace draft edits when the Account broker emits intermediate states.
    property int loadedSettingsVersion: -1
    readonly property bool settingsDirty: instructions.text !== String(cloudPersonalization.settings.personalInstructions || "")
                                          || memoryToggle.checked !== (cloudPersonalization.settings.memoryEnabled !== false)

    ColumnLayout {
        width: root.availableWidth
        spacing: 14 * root.uiScale
        anchors.margins: 22 * root.uiScale

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: cloudHeader.implicitHeight + 28 * root.uiScale
            radius: 20 * root.uiScale
            color: MeoTheme.surfaceContainerLow

            ColumnLayout {
                id: cloudHeader
                anchors.fill: parent
                anchors.margins: 14 * root.uiScale
                spacing: 8 * root.uiScale
                RowLayout {
                    Layout.fillWidth: true
                    MeoIcon { icon: "cloud_sync"; size: 28; color: MeoTheme.primary }
                    MeoText {
                        Layout.fillWidth: true
                        text: qsTr("Meo Account personalization")
                        typeRole: "title"; typeSize: "small"
                        color: MeoTheme.contentOnSurface
                    }
                    MeoButton {
                        text: qsTr("Refresh")
                        type: "tonal"; size: "xs"
                        enabled: cloudPersonalization.signedIn && !cloudPersonalization.busy
                        onClicked: cloudPersonalization.refresh(cloudPersonalization.archived)
                    }
                }
                MeoText {
                    Layout.fillWidth: true
                    text: cloudPersonalization.status
                    typeRole: "body"; typeSize: "small"
                    color: MeoTheme.contentOnSurfaceVariant
                    wrapMode: Text.Wrap
                }
                MeoText {
                    Layout.fillWidth: true
                    text: qsTr("Account memories sync between devices. On-device AgentService memory is managed separately.")
                    typeRole: "label"; typeSize: "small"
                    color: MeoTheme.contentOnSurfaceVariant
                    wrapMode: Text.Wrap
                }
            }
        }

        MeoText {
            text: qsTr("Personal instructions")
            typeRole: "title"; typeSize: "small"
            color: MeoTheme.contentOnSurface
        }
        TextArea {
            id: instructions
            Layout.fillWidth: true
            Layout.preferredHeight: 126 * root.uiScale
            placeholderText: qsTr("How should Meo AI respond to you?")
            wrapMode: TextEdit.Wrap
            selectByMouse: true
            color: MeoTheme.contentOnSurface
            text: ""
            enabled: cloudPersonalization.signedIn && !cloudPersonalization.busy
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 10 * root.uiScale
            MeoText {
                text: String(instructions.length) + " / 5000"
                typeRole: "label"; typeSize: "small"
                color: MeoTheme.contentOnSurfaceVariant
            }
            Item { Layout.fillWidth: true }
            Switch {
                id: memoryToggle
                text: qsTr("Use saved memories")
                checked: true
                enabled: cloudPersonalization.signedIn && !cloudPersonalization.busy
            }
            MeoButton {
                text: qsTr("Save")
                type: "filled"; size: "s"
                enabled: cloudPersonalization.signedIn && !cloudPersonalization.busy
                         && root.settingsDirty && instructions.length <= 5000
                onClicked: cloudPersonalization.saveSettings(instructions.text, memoryToggle.checked)
            }
        }

        Rectangle {
            Layout.fillWidth: true
            height: Math.max(1, root.uiScale)
            color: MeoTheme.outlineVariant
        }
        RowLayout {
            Layout.fillWidth: true
            MeoText {
                Layout.fillWidth: true
                text: cloudPersonalization.archived ? qsTr("Archived memories") : qsTr("Saved memories")
                typeRole: "title"; typeSize: "small"
                color: MeoTheme.contentOnSurface
            }
            MeoButton {
                text: cloudPersonalization.archived ? qsTr("Active") : qsTr("Archive")
                type: "outlined"; size: "xs"
                enabled: cloudPersonalization.signedIn && !cloudPersonalization.busy
                onClicked: cloudPersonalization.refresh(!cloudPersonalization.archived)
            }
        }
        MeoText {
            Layout.fillWidth: true
            text: qsTr("Disable or archive a memory to stop using it in future AI model requests.")
            typeRole: "body"; typeSize: "small"
            color: MeoTheme.contentOnSurfaceVariant
            wrapMode: Text.Wrap
        }
        RowLayout {
            Layout.fillWidth: true
            visible: !cloudPersonalization.archived
            spacing: 8 * root.uiScale
            TextField {
                id: newMemory
                Layout.fillWidth: true
                placeholderText: qsTr("Add a personal memory…")
                maximumLength: 2000
                enabled: cloudPersonalization.signedIn && !cloudPersonalization.busy
            }
            MeoButton {
                text: qsTr("Add")
                type: "tonal"; size: "s"
                enabled: cloudPersonalization.signedIn && !cloudPersonalization.busy
                         && newMemory.text.trim().length > 0
                // Keep the draft on HTTP 409, 401 or network failure.
                // memoryCreated is emitted only after confirmed API success.
                onClicked: cloudPersonalization.addMemory(newMemory.text)
            }
        }

        Repeater {
            model: cloudPersonalization.memories
            delegate: Rectangle {
                required property var modelData
                Layout.fillWidth: true
                implicitHeight: memoryColumn.implicitHeight + 22 * root.uiScale
                radius: 18 * root.uiScale
                color: MeoTheme.surfaceContainerLow

                ColumnLayout {
                    id: memoryColumn
                    anchors.fill: parent
                    anchors.margins: 12 * root.uiScale
                    spacing: 8 * root.uiScale
                    MeoText {
                        Layout.fillWidth: true
                        text: String(modelData.content || "")
                        typeRole: "body"; typeSize: "medium"
                        color: MeoTheme.contentOnSurface
                        wrapMode: Text.Wrap
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 7 * root.uiScale
                        MeoText {
                            Layout.fillWidth: true
                            text: String(modelData.kind || "fact")
                                  + (modelData.enabled === false ? qsTr(" · disabled") : "")
                            typeRole: "label"; typeSize: "small"
                            color: MeoTheme.contentOnSurfaceVariant
                        }
                        MeoButton {
                            text: qsTr("Edit")
                            type: "text"; size: "xs"
                            enabled: !cloudPersonalization.busy
                            onClicked: {
                                root.editingId = String(modelData.id)
                                root.editingVersion = Number(modelData.version)
                                editMemoryField.text = String(modelData.content || "")
                                editDialog.open()
                            }
                        }
                        MeoButton {
                            visible: !cloudPersonalization.archived
                            text: modelData.enabled === false ? qsTr("Enable") : qsTr("Disable")
                            type: "text"; size: "xs"
                            enabled: !cloudPersonalization.busy
                            onClicked: cloudPersonalization.setMemoryEnabled(
                                String(modelData.id), Number(modelData.version),
                                modelData.enabled !== true)
                        }
                        MeoButton {
                            text: cloudPersonalization.archived ? qsTr("Restore") : qsTr("Archive")
                            type: "text"; size: "xs"
                            enabled: !cloudPersonalization.busy
                            onClicked: cloudPersonalization.archiveMemory(
                                String(modelData.id), Number(modelData.version),
                                !cloudPersonalization.archived)
                        }
                        MeoButton {
                            text: qsTr("Delete")
                            type: "text"; size: "xs"
                            enabled: !cloudPersonalization.busy
                            onClicked: {
                                root.deletingId = String(modelData.id)
                                deleteDialog.open()
                            }
                        }
                    }
                }
            }
        }
        MeoText {
            Layout.fillWidth: true
            visible: cloudPersonalization.signedIn && cloudPersonalization.memories.length === 0
            text: cloudPersonalization.archived ? qsTr("No archived memories.") : qsTr("No memories saved yet.")
            typeRole: "body"; typeSize: "small"
            color: MeoTheme.contentOnSurfaceVariant
        }
        Item { Layout.fillHeight: true; Layout.minimumHeight: 8 * root.uiScale }
    }

    Dialog {
        id: editDialog
        title: qsTr("Edit memory")
        modal: true
        anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.Ok | Dialog.Cancel
        width: Math.min(520 * root.uiScale, root.width - 32 * root.uiScale)
        onAccepted: {
            const updated = editMemoryField.text.trim()
            if (updated.length > 0 && updated.length <= 2000)
                cloudPersonalization.updateMemory(root.editingId, root.editingVersion, updated)
        }
        TextArea {
            id: editMemoryField
            width: parent.width
            height: 150 * root.uiScale
            wrapMode: TextEdit.Wrap
            selectByMouse: true
            color: MeoTheme.contentOnSurface
        }
    }

    Dialog {
        id: deleteDialog
        title: qsTr("Permanently delete memory?")
        modal: true
        anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.Yes | Dialog.No
        onAccepted: cloudPersonalization.deleteMemory(root.deletingId)
        MeoText {
            text: qsTr("This memory cannot be recovered after deletion.")
            typeRole: "body"; typeSize: "small"
            color: MeoTheme.contentOnSurfaceVariant
        }
    }

    Connections {
        target: cloudPersonalization
        function onMemoryCreated() {
            newMemory.clear()
        }
        function onChanged() {
            if (!cloudPersonalization.signedIn) {
                root.loadedSettingsVersion = -1
                instructions.text = ""
                memoryToggle.checked = true
                return
            }
            const data = cloudPersonalization.settings
            const version = Number(data.version ?? -1)
            // Broker busy / network signals must not wipe unsaved text or a
            // changed toggle. Apply server state only after its version advances.
            if (version >= 0 && version !== root.loadedSettingsVersion) {
                root.loadedSettingsVersion = version
                instructions.text = String(data.personalInstructions || "")
                memoryToggle.checked = data.memoryEnabled !== false
            }
        }
    }
}

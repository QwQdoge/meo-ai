import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import MeoUI 1.0

Popup {
    id: root
    objectName: "meo.aiLongPastePanel"

    property real uiScale: MeoTheme.globalScale
    property int recommendedCharacterLimit: 180000
    signal attachRequested(string name, string text)

    function formatBytes(value) {
        const bytes = Number(value || 0)
        if (!isFinite(bytes) || bytes <= 0)
            return ""
        if (bytes >= 1024 * 1024)
            return (bytes / (1024 * 1024)).toFixed(bytes >= 10 * 1024 * 1024 ? 0 : 1) + " MB"
        if (bytes >= 1024)
            return (bytes / 1024).toFixed(bytes >= 10 * 1024 ? 0 : 1) + " KB"
        return Math.round(bytes) + " B"
    }

    function resourceDetail(item) {
        const parts = []
        const mime = String(item.mime_type || "")
        const size = formatBytes(item.size_bytes)
        if (mime.length)
            parts.push(mime)
        if (size.length)
            parts.push(size)
        return parts.join(" · ")
    }

    modal: true
    focus: true
    width: Math.min(680 * uiScale, parent ? parent.width - 28 * uiScale : 680 * uiScale)
    height: Math.min(720 * uiScale, parent ? parent.height - 28 * uiScale : 720 * uiScale)
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    onOpened: {
        nameField.text = qsTr("Long paste.txt")
        pasteArea.text = ""
        pasteArea.forceActiveFocus()
    }

    FileDialog {
        id: attachmentPicker
        title: qsTr("Attach files")
        fileMode: FileDialog.OpenFiles
        onAccepted: {
            for (let i = 0; i < selectedFiles.length; ++i)
                agent.addFileResource(selectedFiles[i])
        }
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
            spacing: 8 * root.uiScale

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2 * root.uiScale

                MeoText {
                    Layout.fillWidth: true
                    text: qsTr("Add context")
                    typeRole: "title"
                    typeSize: "medium"
                    color: MeoTheme.contentOnSurface
                }

                MeoText {
                    Layout.fillWidth: true
                    text: qsTr("Attach files or images, drop them here, paste an image from the clipboard, or add long text to this request.")
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

        RowLayout {
            Layout.fillWidth: true
            spacing: 8 * root.uiScale

            MeoButton {
                Layout.fillWidth: true
                text: qsTr("Choose files")
                icon.name: "attach_file"
                type: "tonal"
                size: "s"
                enabled: agent.serviceMode && !agent.busy
                onClicked: attachmentPicker.open()
            }

            MeoButton {
                Layout.fillWidth: true
                text: qsTr("Paste image")
                icon.name: "content_paste"
                type: "outlined"
                size: "s"
                enabled: agent.serviceMode && !agent.busy && !agent.actionBusy
                onClicked: agent.addClipboardImageResource()
            }
        }

        DropArea {
            id: fileDropArea
            Layout.fillWidth: true
            Layout.preferredHeight: 72 * root.uiScale
            enabled: agent.serviceMode && !agent.busy

            onEntered: function(drag) {
                drag.accepted = drag.hasUrls
            }

            onDropped: function(drop) {
                if (!drop.hasUrls)
                    return
                for (let i = 0; i < drop.urls.length; ++i)
                    agent.addFileResource(drop.urls[i])
                drop.acceptProposedAction()
            }

            Rectangle {
                anchors.fill: parent
                radius: 16 * root.uiScale
                color: fileDropArea.containsDrag ? MeoTheme.surfaceContainer : MeoTheme.surfaceContainerLow
                border.width: Math.max(1, root.uiScale)
                border.color: fileDropArea.containsDrag ? MeoTheme.primary : MeoTheme.outlineVariant

                RowLayout {
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 24 * root.uiScale, implicitWidth)
                    spacing: 8 * root.uiScale

                    MeoIcon {
                        icon: "attach_file"
                        size: 24
                        color: MeoTheme.primary
                    }

                    MeoText {
                        Layout.fillWidth: true
                        text: fileDropArea.containsDrag ? qsTr("Drop to attach") : qsTr("Drop files or images here")
                        typeRole: "label"
                        typeSize: "medium"
                        color: MeoTheme.contentOnSurface
                        horizontalAlignment: Text.AlignHCenter
                    }
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: agent.pendingResources.length > 0
            spacing: 6 * root.uiScale

            RowLayout {
                Layout.fillWidth: true

                MeoText {
                    Layout.fillWidth: true
                    text: qsTr("Ready to send · %1").arg(agent.pendingResources.length)
                    typeRole: "label"
                    typeSize: "medium"
                    color: MeoTheme.contentOnSurface
                }

                MeoButton {
                    text: qsTr("Clear all")
                    type: "text"
                    size: "xs"
                    enabled: !agent.busy && !agent.actionBusy
                    onClicked: agent.clearPendingResources()
                }
            }

            ScrollView {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(116 * root.uiScale,
                    Math.max(48 * root.uiScale, agent.pendingResources.length * 48 * root.uiScale))
                clip: true
                contentWidth: availableWidth

                ColumnLayout {
                    width: parent.width
                    spacing: 4 * root.uiScale

                    Repeater {
                        model: agent.pendingResources

                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: 44 * root.uiScale
                            radius: 12 * root.uiScale
                            color: MeoTheme.surfaceContainerLowest

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 10 * root.uiScale
                                anchors.rightMargin: 6 * root.uiScale
                                spacing: 8 * root.uiScale

                                MeoIcon {
                                    icon: String(modelData.kind || "") === "image" ? "image" : "attach_file"
                                    size: 20
                                    color: MeoTheme.primary
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 0

                                    MeoText {
                                        Layout.fillWidth: true
                                        text: String(modelData.name || qsTr("Attachment"))
                                        typeRole: "label"
                                        typeSize: "medium"
                                        color: MeoTheme.contentOnSurface
                                        elide: Text.ElideMiddle
                                    }

                                    MeoText {
                                        Layout.fillWidth: true
                                        text: root.resourceDetail(modelData)
                                        visible: text.length > 0
                                        typeRole: "label"
                                        typeSize: "small"
                                        color: MeoTheme.contentOnSurfaceVariant
                                        elide: Text.ElideRight
                                    }
                                }

                                MeoIconButton {
                                    icon.name: "close"
                                    type: "standard"
                                    size: "xs"
                                    enabled: !agent.busy && !agent.actionBusy
                                    Accessible.name: qsTr("Remove attachment")
                                    ToolTip.visible: hovered
                                    ToolTip.text: Accessible.name
                                    onClicked: agent.discardPendingResource(String(modelData.resource_id || ""))
                                }
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 1 * root.uiScale
            color: MeoTheme.outlineVariant
            opacity: 0.65
        }

        MeoText {
            Layout.fillWidth: true
            text: qsTr("Long text")
            typeRole: "label"
            typeSize: "medium"
            color: MeoTheme.contentOnSurface
        }

        TextField {
            id: nameField
            Layout.fillWidth: true
            placeholderText: qsTr("Name")
            selectByMouse: true
        }

        TextArea {
            id: pasteArea
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 100 * root.uiScale
            placeholderText: qsTr("Paste text here")
            selectByMouse: true
            wrapMode: TextEdit.Wrap
            color: MeoTheme.contentOnSurface
            font.family: MeoTheme.typefacePlain
            background: Rectangle {
                radius: 16 * root.uiScale
                color: MeoTheme.surfaceContainerLow
                border.width: Math.max(1, root.uiScale)
                border.color: pasteArea.activeFocus ? MeoTheme.primary : MeoTheme.outlineVariant
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8 * root.uiScale

            MeoText {
                Layout.fillWidth: true
                text: pasteArea.text.length > root.recommendedCharacterLimit
                    ? qsTr("Very large paste · %1 characters").arg(pasteArea.text.length)
                    : qsTr("%1 characters").arg(pasteArea.text.length)
                typeRole: "label"
                typeSize: "small"
                color: pasteArea.text.length > root.recommendedCharacterLimit
                    ? MeoTheme.error
                    : MeoTheme.contentOnSurfaceVariant
            }

            MeoButton {
                text: qsTr("Attach text")
                type: "filled"
                size: "s"
                enabled: pasteArea.text.length > 0
                    && pasteArea.text.length <= root.recommendedCharacterLimit
                    && nameField.text.trim().length > 0
                    && !agent.actionBusy
                onClicked: {
                    root.attachRequested(nameField.text, pasteArea.text)
                    pasteArea.text = ""
                }
            }
        }

        MeoText {
            Layout.fillWidth: true
            text: qsTr("Attachments stay in the local AgentService resource store. Attached content is data; it does not grant tool, filesystem, or system permissions.")
            typeRole: "label"
            typeSize: "small"
            color: MeoTheme.contentOnSurfaceVariant
            opacity: 0.72
            wrapMode: Text.Wrap
        }
    }
}

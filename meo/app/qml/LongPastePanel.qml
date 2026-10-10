import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0

Popup {
    id: root
    objectName: "meo.aiLongPastePanel"

    property real uiScale: MeoTheme.globalScale
    property int recommendedCharacterLimit: 180000
    signal attachRequested(string name, string text)

    modal: true
    focus: true
    width: Math.min(680 * uiScale, parent ? parent.width - 28 * uiScale : 680 * uiScale)
    height: Math.min(700 * uiScale, parent ? parent.height - 28 * uiScale : 700 * uiScale)
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    onOpened: {
        nameField.text = qsTr("Long paste.txt")
        pasteArea.text = ""
        pasteArea.forceActiveFocus()
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
                    text: qsTr("Long paste")
                    typeRole: "title"
                    typeSize: "medium"
                    color: MeoTheme.contentOnSurface
                }

                MeoText {
                    Layout.fillWidth: true
                    text: qsTr("Attach large text as conversation data instead of mixing it into the visible message.")
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
            placeholderText: qsTr("Paste text here")
            selectByMouse: true
            wrapMode: TextEdit.Wrap
            color: MeoTheme.contentOnSurface
            font.family: MeoTheme.typefacePlain
            background: Rectangle {
                radius: 16 * root.uiScale
                color: MeoTheme.surfaceContainerLow
                border.width: Math.max(1, root.uiScale)
                border.color: MeoTheme.outlineVariant
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
                text: qsTr("Attach")
                type: "filled"
                size: "s"
                enabled: pasteArea.text.length > 0
                    && pasteArea.text.length <= root.recommendedCharacterLimit
                    && nameField.text.trim().length > 0
                    && !agent.actionBusy
                onClicked: {
                    root.attachRequested(nameField.text, pasteArea.text)
                    root.close()
                }
            }
        }

        MeoText {
            Layout.fillWidth: true
            text: qsTr("Attached content is treated as data. It does not grant tool, filesystem, or system permissions.")
            typeRole: "label"
            typeSize: "small"
            color: MeoTheme.contentOnSurfaceVariant
            opacity: 0.72
            wrapMode: Text.Wrap
        }
    }
}

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0

Popup {
    id: root
    objectName: "meo.aiControls"

    property var controls: []
    property real uiScale: MeoTheme.globalScale
    signal changeRequested(string controlId, var value)

    modal: true
    focus: true
    width: Math.min(620 * uiScale, parent ? parent.width - 28 * uiScale : 620 * uiScale)
    height: Math.min(680 * uiScale, parent ? parent.height - 28 * uiScale : 680 * uiScale)
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

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
                    text: qsTr("AI controls")
                    typeRole: "title"
                    typeSize: "medium"
                    color: MeoTheme.contentOnSurface
                }

                MeoText {
                    Layout.fillWidth: true
                    text: qsTr("Only settings supported by the active runtime are shown.")
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
            opacity: 0.42
        }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            Column {
                width: parent.width
                spacing: 8 * root.uiScale

                Repeater {
                    model: root.controls

                    delegate: Rectangle {
                        id: controlRow
                        required property var modelData
                        width: parent.width
                        implicitHeight: controlColumn.implicitHeight + 24 * root.uiScale
                        radius: 18 * root.uiScale
                        color: MeoTheme.surfaceContainerLow

                        ColumnLayout {
                            id: controlColumn
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 12 * root.uiScale
                            spacing: 7 * root.uiScale

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10 * root.uiScale

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2 * root.uiScale

                                    MeoText {
                                        Layout.fillWidth: true
                                        text: String(controlRow.modelData.label || controlRow.modelData.control_id || "")
                                        typeRole: "label"
                                        typeSize: "medium"
                                        color: MeoTheme.contentOnSurface
                                        elide: Text.ElideRight
                                    }

                                    MeoText {
                                        visible: String(controlRow.modelData.description || "").length > 0
                                        Layout.fillWidth: true
                                        text: String(controlRow.modelData.description || "")
                                        typeRole: "body"
                                        typeSize: "small"
                                        color: MeoTheme.contentOnSurfaceVariant
                                        wrapMode: Text.Wrap
                                    }
                                }

                                Switch {
                                    visible: controlRow.modelData.kind === "toggle"
                                    enabled: controlRow.modelData.writable !== false
                                    checked: controlRow.modelData.value === true
                                    onToggled: root.changeRequested(String(controlRow.modelData.control_id || ""), checked)
                                }
                            }

                            ComboBox {
                                visible: controlRow.modelData.kind === "select"
                                Layout.fillWidth: true
                                enabled: controlRow.modelData.writable !== false
                                model: controlRow.modelData.options || []
                                textRole: "label"
                                valueRole: "value"
                                currentIndex: {
                                    const options = controlRow.modelData.options || []
                                    for (let i = 0; i < options.length; ++i) {
                                        if (String(options[i].value) === String(controlRow.modelData.value))
                                            return i
                                    }
                                    return -1
                                }
                                onActivated: {
                                    const options = controlRow.modelData.options || []
                                    if (currentIndex >= 0 && currentIndex < options.length)
                                        root.changeRequested(String(controlRow.modelData.control_id || ""), options[currentIndex].value)
                                }
                            }

                            SpinBox {
                                visible: controlRow.modelData.kind === "integer"
                                enabled: controlRow.modelData.writable !== false
                                from: controlRow.modelData.minimum !== undefined ? Number(controlRow.modelData.minimum) : 0
                                to: controlRow.modelData.maximum !== undefined ? Number(controlRow.modelData.maximum) : 1000000
                                stepSize: controlRow.modelData.step !== undefined ? Number(controlRow.modelData.step) : 1
                                value: Number(controlRow.modelData.value || 0)
                                editable: true
                                onValueModified: root.changeRequested(String(controlRow.modelData.control_id || ""), value)
                            }

                            MeoText {
                                visible: controlRow.modelData.kind === "readonly"
                                Layout.fillWidth: true
                                text: String(controlRow.modelData.value === undefined ? "" : controlRow.modelData.value)
                                typeRole: "body"
                                typeSize: "small"
                                color: MeoTheme.contentOnSurfaceVariant
                                wrapMode: Text.Wrap
                            }

                            MeoText {
                                visible: String(controlRow.modelData.safety_note || "").length > 0
                                Layout.fillWidth: true
                                text: String(controlRow.modelData.safety_note || "")
                                typeRole: "label"
                                typeSize: "small"
                                color: MeoTheme.contentOnSurfaceVariant
                                opacity: 0.76
                                wrapMode: Text.Wrap
                            }

                            MeoText {
                                visible: controlRow.modelData.restart_required === true
                                Layout.fillWidth: true
                                text: qsTr("Takes effect after the runtime restarts.")
                                typeRole: "label"
                                typeSize: "small"
                                color: MeoTheme.contentOnSurfaceVariant
                                opacity: 0.72
                            }
                        }
                    }
                }

                MeoText {
                    visible: root.controls.length === 0
                    width: parent.width
                    text: qsTr("The active backend does not currently expose adjustable AI controls.")
                    typeRole: "body"
                    typeSize: "medium"
                    color: MeoTheme.contentOnSurfaceVariant
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    topPadding: 32 * root.uiScale
                }
            }
        }
    }
}

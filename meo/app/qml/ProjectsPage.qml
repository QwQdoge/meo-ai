import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0

Item {
    id: root
    objectName: "meoAiProjectsPage"

    property var store: null
    property real uiScale: MeoTheme.globalScale
    property bool creating: false
    readonly property var projectList: store ? store.projects : []

    ColumnLayout {
        anchors.fill: parent
        spacing: 14 * root.uiScale

        RowLayout {
            Layout.fillWidth: true
            spacing: 12 * root.uiScale

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4 * root.uiScale

                MeoText {
                    text: qsTr("Projects")
                    typeRole: "title"
                    typeSize: "big"
                    color: MeoTheme.contentOnSurface
                }
                MeoText {
                    Layout.fillWidth: true
                    text: qsTr("Keep related chats, files and Work together in one persistent place.")
                    typeRole: "body"
                    typeSize: "small"
                    color: MeoTheme.contentOnSurfaceVariant
                    wrapMode: Text.Wrap
                }
            }

            MeoButton {
                objectName: "meoAiNewProject"
                text: root.creating ? qsTr("Cancel") : qsTr("New project")
                icon.name: root.creating ? "close" : "add"
                type: root.creating ? "text" : "filled"
                size: "s"
                onClicked: {
                    root.creating = !root.creating
                    if (root.creating)
                        Qt.callLater(function() { projectName.forceActiveFocus() })
                    else
                        projectName.text = ""
                }
            }
        }

        Rectangle {
            visible: root.creating
            Layout.fillWidth: true
            implicitHeight: createRow.implicitHeight + 28 * root.uiScale
            radius: 20 * root.uiScale
            color: MeoTheme.surfaceContainerLow
            border.width: Math.max(1, root.uiScale)
            border.color: MeoTheme.outlineVariant

            RowLayout {
                id: createRow
                anchors.fill: parent
                anchors.margins: 14 * root.uiScale
                spacing: 10 * root.uiScale

                MeoTextField {
                    id: projectName
                    objectName: "meoAiProjectName"
                    Layout.fillWidth: true
                    placeholder: qsTr("Project name")
                    size: "s"
                    Accessible.name: qsTr("Project name")
                }

                MeoButton {
                    objectName: "meoAiCreateProject"
                    text: qsTr("Create")
                    type: "filled"
                    size: "s"
                    enabled: !!root.store && projectName.text.trim().length > 0
                    onClicked: {
                        if (!root.store)
                            return
                        const id = root.store.createProject(projectName.text)
                        if (!id.length)
                            return
                        projectName.text = ""
                        root.creating = false
                    }
                }
            }
        }

        Rectangle {
            visible: root.projectList.length === 0 && !root.creating
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: 24 * root.uiScale
            color: MeoTheme.surfaceContainerLow

            ColumnLayout {
                width: Math.min(parent.width - 48 * root.uiScale, 520 * root.uiScale)
                anchors.centerIn: parent
                spacing: 10 * root.uiScale

                MeoIcon {
                    Layout.alignment: Qt.AlignHCenter
                    icon: "folder_open"
                    size: 36
                    color: MeoTheme.primary
                }
                MeoText {
                    Layout.fillWidth: true
                    text: qsTr("No projects yet")
                    typeRole: "title"
                    typeSize: "medium"
                    horizontalAlignment: Text.AlignHCenter
                    color: MeoTheme.contentOnSurface
                }
                MeoText {
                    Layout.fillWidth: true
                    text: qsTr("Create one now. Chats and Work can be attached to it in the next project step.")
                    typeRole: "body"
                    typeSize: "small"
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    color: MeoTheme.contentOnSurfaceVariant
                }
            }
        }

        ListView {
            id: projectListView
            objectName: "meoAiProjectList"
            visible: root.projectList.length > 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 10 * root.uiScale
            model: root.projectList
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Rectangle {
                required property var modelData
                width: projectListView.width
                height: projectRow.implicitHeight + 28 * root.uiScale
                radius: 20 * root.uiScale
                color: root.store && root.store.activeProjectId === String(modelData.id)
                    ? MeoTheme.secondaryContainer
                    : MeoTheme.surfaceContainerLow
                border.width: Math.max(1, root.uiScale)
                border.color: root.store && root.store.activeProjectId === String(modelData.id)
                    ? MeoTheme.primary
                    : MeoTheme.outlineVariant

                RowLayout {
                    id: projectRow
                    anchors.fill: parent
                    anchors.margins: 14 * root.uiScale
                    spacing: 12 * root.uiScale

                    Rectangle {
                        Layout.preferredWidth: 44 * root.uiScale
                        Layout.preferredHeight: 44 * root.uiScale
                        radius: 15 * root.uiScale
                        color: MeoTheme.surfaceContainer
                        MeoIcon {
                            anchors.centerIn: parent
                            icon: "folder_open"
                            size: 24
                            color: MeoTheme.primary
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3 * root.uiScale
                        MeoText {
                            Layout.fillWidth: true
                            text: String(modelData.name || "")
                            typeRole: "title"
                            typeSize: "small"
                            elide: Text.ElideRight
                            color: MeoTheme.contentOnSurface
                        }
                        MeoText {
                            Layout.fillWidth: true
                            text: root.store && root.store.activeProjectId === String(modelData.id)
                                ? qsTr("Current project")
                                : qsTr("Persistent project context")
                            typeRole: "label"
                            typeSize: "small"
                            color: MeoTheme.contentOnSurfaceVariant
                        }
                    }

                    MeoButton {
                        objectName: "meoAiOpenProject-" + String(modelData.id || "")
                        text: root.store && root.store.activeProjectId === String(modelData.id)
                            ? qsTr("Active")
                            : qsTr("Open")
                        type: root.store && root.store.activeProjectId === String(modelData.id) ? "tonal" : "outlined"
                        size: "s"
                        enabled: !!root.store && root.store.activeProjectId !== String(modelData.id)
                        onClicked: root.store.openProject(String(modelData.id))
                    }
                }
            }
        }
    }
}

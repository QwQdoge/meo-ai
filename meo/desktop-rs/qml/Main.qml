// Generic renderer for the Meo AI core view (meo_ai_core::cloud::app).
// It knows only component kinds, never product features: navigation entries,
// pages, settings and buttons all come from `core.view`. Every interaction
// sends the action object attached to the element back to the core.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0

ApplicationWindow {
    id: window
    width: 1180
    height: 780
    minimumWidth: 720
    minimumHeight: 520
    visible: true
    title: "Meo AI"

    required property var core
    color: MeoTheme.background

    readonly property var v: (core && core.view) || ({})
    readonly property var page: v.page || ({})
    readonly property var prefs: v.prefs || ({})

    Connections {
        target: window.core
        function onActivateRequested() {
            window.show()
            window.raise()
            window.requestActivate()
        }
    }

    function act(action) {
        if (action)
            core.dispatch(JSON.stringify(action))
    }

    function withFields(action, fields) {
        const copy = Object.assign({}, action)
        for (const key in fields)
            copy[key] = fields[key]
        return copy
    }

    // Generic modal question from the core (`view.dialog`): kind "prompt" has a text field.
    MeoDialog {
        id: appDialog
        readonly property var spec: window.v.dialog || null
        readonly property string specKey: spec ? JSON.stringify(spec) : ""
        property string inputValue: ""
        title: spec ? spec.title : ""
        message: spec && spec.text ? spec.text : ""
        confirmText: spec && spec.actions[0] ? spec.actions[0].label : ""
        cancelText: spec && spec.actions[1] ? spec.actions[1].label : ""
        supportingContent: spec && spec.input ? promptField : null
        onSpecKeyChanged: {
            if (spec) {
                inputValue = spec.input ? (spec.input.value || "") : ""
                open()
            } else {
                close()
            }
        }
        onConfirmed: {
            const a = spec.actions[0]
            window.act(a.withInput ? window.withFields(a.action, { text: inputValue }) : a.action)
        }
        onCancelled: if (spec && spec.actions[1]) window.act(spec.actions[1].action)
        onDismissed: if (spec && !dismissedByAction) window.act({ type: "close_dialog" })
    }

    Component {
        id: promptField
        MeoTextField {
            width: 320
            placeholder: appDialog.spec && appDialog.spec.input ? appDialog.spec.input.placeholder : ""
            text: appDialog.inputValue
            onTextChanged: appDialog.inputValue = text
            Component.onCompleted: forceActiveFocus()
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        MeoNavigationRail {
            visible: (window.v.navigation || []).length > 0
            Layout.fillHeight: true
            model: (window.v.navigation || []).map(n => ({ id: n.id, icon: n.symbol, label: n.label }))
            currentId: ((window.v.navigation || []).find(n => n.selected) || {}).id || ""
            onActivated: (item, index) => window.act(window.v.navigation[index].action)
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            MeoBanner {
                visible: !!window.v.notice
                Layout.fillWidth: true
                Layout.margins: 12
                tone: window.v.notice && window.v.notice.kind === "error" ? "error" : "tonal"
                text: window.v.notice ? window.v.notice.text : ""
                confirmText: qsTr("Dismiss")
                onConfirmed: window.act(window.v.notice.action)
            }

            MeoBanner {
                visible: window.v.online === false
                Layout.fillWidth: true
                Layout.margins: 12
                tone: "warning"
                icon: "cloud_off"
                text: qsTr("Offline — showing saved data")
            }

            Loader {
                Layout.fillWidth: true
                Layout.fillHeight: true
                sourceComponent: ({
                    sign_in: signInPage,
                    conversation: conversationPage,
                    list: listPage,
                    settings: settingsPage,
                    unavailable: unavailablePage,
                })[window.page.kind] || unavailablePage
            }
        }
    }

    component ActionButton: MeoButton {
        property var spec: ({})
        text: spec.label || ""
        type: spec.style === "primary" ? "filled" : spec.style === "danger" ? "outlined" : "tonal"
        onClicked: window.act(spec.action)
    }

    Component {
        id: signInPage
        Item {
            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width - 48, 420)
                spacing: 20
                MeoAiMark { Layout.alignment: Qt.AlignHCenter; implicitWidth: 72; implicitHeight: 72 }
                MeoText { text: window.page.title; typeRole: "title"; typeSize: "big"; Layout.alignment: Qt.AlignHCenter }
                MeoText {
                    text: window.page.text
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                    Layout.fillWidth: true
                    color: MeoTheme.onSurfaceVariant
                }
                MeoLoadingIndicator { visible: !!window.page.busy; Layout.alignment: Qt.AlignHCenter }
                Repeater {
                    model: window.page.actions || []
                    ActionButton { spec: modelData; Layout.alignment: Qt.AlignHCenter }
                }
            }
        }
    }

    Component {
        id: unavailablePage
        Item {
            MeoEmptyState {
                anchors.centerIn: parent
                width: Math.min(parent.width - 48, 480)
                icon: "info"
                title: window.page.title || ""
                description: window.page.text || ""
                actionText: (window.page.actions || [])[0] ? window.page.actions[0].label : ""
                onActionClicked: window.act(window.page.actions[0].action)
            }
        }
    }

    Component {
        id: listPage
        ColumnLayout {
            spacing: 8
            RowLayout {
                Layout.fillWidth: true
                Layout.margins: 24
                MeoText { text: window.page.title || ""; typeRole: "title"; typeSize: "big"; Layout.fillWidth: true }
                Repeater { model: window.page.actions || []; ActionButton { spec: modelData } }
            }
            MeoLoadingIndicator { visible: !!window.page.loading; Layout.alignment: Qt.AlignHCenter }
            MeoEmptyState {
                visible: !!window.page.empty
                Layout.alignment: Qt.AlignHCenter
                title: window.page.empty ? window.page.empty.title : ""
            }
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.leftMargin: 16
                Layout.rightMargin: 16
                clip: true
                spacing: 4
                model: window.page.items || []
                delegate: MeoListItem {
                    width: ListView.view.width
                    headline: modelData.title || ""
                    supportingText: modelData.subtitle || ""
                    interactive: !!modelData.action
                    onClicked: window.act(modelData.action)
                }
            }
        }
    }

    Component {
        id: settingsPage
        Flickable {
            contentHeight: settingsColumn.implicitHeight + 48
            clip: true
            ColumnLayout {
                id: settingsColumn
                x: 24
                y: 24
                width: Math.min(parent.width - 48, 720)
                spacing: 24
                MeoText { text: window.page.title || ""; typeRole: "title"; typeSize: "big" }
                Repeater {
                    model: window.page.sections || []
                    ColumnLayout {
                        id: section
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 8
                        MeoText { text: section.modelData.label; typeRole: "title"; typeSize: "small"; color: MeoTheme.primary }
                        Repeater {
                            model: section.modelData.items
                            SettingControl { required property var modelData; item: modelData; Layout.fillWidth: true }
                        }
                    }
                }
            }
        }
    }

    component SettingControl: ColumnLayout {
        property var item: ({})
        spacing: 4

        MeoSwitch {
            visible: item.kind === "toggle"
            Layout.fillWidth: true
            text: item.label || ""
            checked: item.value === true
            onToggled: checked => window.act({ type: "set_setting", binding: item.binding, value: checked })
        }
        MeoExposedDropdown {
            visible: item.kind === "select"
            Layout.fillWidth: true
            label: item.label || ""
            model: item.options || []
            textRole: "label"
            valueRole: "value"
            currentIndex: (item.options || []).findIndex(o => o.value === item.value)
            onSelected: (index, value) => window.act({ type: "set_setting", binding: item.binding, value: item.options[index].value })
        }
        MeoTextField {
            visible: item.kind === "text" && !!item.single_line
            Layout.fillWidth: true
            label: item.label || ""
            placeholder: item.placeholder || ""
            text: item.value || ""
            onEditingFinished: if (text !== (item.value || "")) window.act({ type: "set_setting", binding: item.binding, value: text })
        }
        MeoTextArea {
            id: textField
            visible: item.kind === "text" && !item.single_line
            Layout.fillWidth: true
            Layout.preferredHeight: 96
            label: item.label || ""
            text: item.value || ""
            onEditingFinished: if (text !== (item.value || "")) window.act({ type: "set_setting", binding: item.binding, value: text })
        }
        RowLayout {
            visible: item.kind === "info"
            Layout.fillWidth: true
            MeoText { text: item.label || ""; Layout.fillWidth: true }
            MeoText { text: String(item.value || ""); color: MeoTheme.onSurfaceVariant }
        }
        ActionButton {
            visible: item.kind === "button"
            spec: ({ label: item.label, style: item.style, action: item.action })
        }
    }

    Component {
        id: conversationPage
        RowLayout {
            spacing: 0

            ColumnLayout {
                Layout.preferredWidth: 280
                Layout.fillHeight: true
                Layout.margins: 12
                spacing: 8
                Repeater {
                    model: (window.page.sidebar || {}).actions || []
                    ActionButton { spec: modelData; Layout.fillWidth: true }
                }
                MeoTextField {
                    id: searchField
                    visible: !!(window.page.sidebar || {}).search
                    Layout.fillWidth: true
                    placeholder: ((window.page.sidebar || {}).search || {}).placeholder || ""
                    leadingIcon: "search"
                    // Typed text wins; the core echoes it back as the saved value.
                    onTextChanged: if (text !== ((window.page.sidebar || {}).search || {}).value) searchTimer.restart()
                    Timer {
                        id: searchTimer
                        interval: 300
                        onTriggered: window.act(window.withFields(window.page.sidebar.search.action, { text: searchField.text }))
                    }
                }
                RowLayout {
                    visible: ((window.page.sidebar || {}).tabs || []).length > 0
                    Layout.fillWidth: true
                    spacing: 8
                    Repeater {
                        model: (window.page.sidebar || {}).tabs || []
                        MeoButton {
                            required property var modelData
                            text: modelData.label
                            type: modelData.selected ? "tonal" : "outlined"
                            size: "xs"
                            onClicked: window.act(modelData.action)
                        }
                    }
                }
                MeoText { text: (window.page.sidebar || {}).title || ""; typeRole: "label"; color: MeoTheme.onSurfaceVariant }
                ListView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 2
                    model: (window.page.sidebar || {}).items || []
                    delegate: Item {
                        id: chatRow
                        required property var modelData
                        width: ListView.view.width
                        implicitHeight: row.implicitHeight
                        MeoListItem {
                            id: row
                            anchors.fill: parent
                            headline: chatRow.modelData.title
                            supportingText: chatRow.modelData.subtitle
                            selected: !!chatRow.modelData.selected
                            onClicked: window.act(chatRow.modelData.action)
                        }
                        MeoIconButton {
                            visible: (chatRow.modelData.menu || []).length > 0
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            type: "standard"
                            size: "xs"
                            icon.name: "more_vert"
                            onClicked: chatMenu.popup()
                        }
                        Menu {
                            id: chatMenu
                            Repeater {
                                model: chatRow.modelData.menu || []
                                MenuItem {
                                    required property var modelData
                                    text: modelData.label
                                    onTriggered: window.act(modelData.action)
                                }
                            }
                        }
                    }
                }
            }

            Rectangle { Layout.fillHeight: true; width: 1; color: MeoTheme.outlineVariant }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0

                MeoText {
                    text: window.page.title || ""
                    typeRole: "title"
                    Layout.margins: 16
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }

                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    MeoEmptyState {
                        visible: !!window.page.empty
                        anchors.centerIn: parent
                        icon: "chat"
                        title: window.page.empty ? window.page.empty.title : ""
                        description: window.page.empty ? window.page.empty.text : ""
                    }

                    ListView {
                        id: messages
                        anchors.fill: parent
                        anchors.margins: 16
                        clip: true
                        spacing: 12
                        model: window.page.messages || []
                        onCountChanged: positionViewAtEnd()
                        onContentHeightChanged: if (atYEnd || window.page.composer.busy) positionViewAtEnd()
                        delegate: Item {
                            width: ListView.view.width
                            implicitHeight: bubble.implicitHeight
                            readonly property bool mine: modelData.role === "user"
                            Rectangle {
                                id: bubble
                                anchors.right: parent.mine ? parent.right : undefined
                                width: Math.min(parent.width * (parent.mine ? 0.75 : 1), body.implicitWidth + 32)
                                implicitHeight: body.implicitHeight + 24
                                radius: 18
                                color: parent.mine ? MeoTheme.secondaryContainer : "transparent"
                                TextEdit {
                                    id: body
                                    x: 16
                                    y: 12
                                    width: Math.min(implicitWidth, messages.width - 32)
                                    readOnly: true
                                    selectByMouse: true
                                    wrapMode: Text.Wrap
                                    textFormat: TextEdit.MarkdownText
                                    text: modelData.text + (modelData.streaming ? " ▍" : "")
                                    color: MeoTheme.onSurface
                                    font.pixelSize: 15
                                }
                            }
                        }
                    }
                }

                MeoBanner {
                    visible: !!window.page.consent
                    Layout.fillWidth: true
                    Layout.margins: 12
                    title: window.page.consent ? window.page.consent.title : ""
                    text: window.page.consent ? window.page.consent.text : ""
                    confirmText: window.page.consent ? window.page.consent.actions[0].label : ""
                    cancelText: window.page.consent ? window.page.consent.actions[1].label : ""
                    onConfirmed: window.act(window.page.consent.actions[0].action)
                    onCancelled: window.act(window.page.consent.actions[1].action)
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.margins: 16
                    spacing: 8
                    readonly property var composer: window.page.composer || ({})

                    Repeater {
                        model: parent.composer.toolbar || []
                        SettingControl {
                            required property var modelData
                            item: modelData
                            Layout.preferredWidth: 240
                            Layout.alignment: Qt.AlignBottom
                        }
                    }

                    MeoTextArea {
                        id: input
                        Layout.fillWidth: true
                        Layout.maximumHeight: 200
                        placeholder: parent.composer.placeholder || ""
                        wrapMode: TextEdit.Wrap
                        Keys.onReturnPressed: event => {
                            const enterSends = window.prefs["general.enter_to_send"] !== false
                            if (enterSends !== !!(event.modifiers & Qt.ShiftModifier)) {
                                send()
                                event.accepted = true
                            } else {
                                event.accepted = false
                            }
                        }
                        function send() {
                            if (!text.trim().length || parent.composer.busy)
                                return
                            window.act(window.withFields(parent.composer.sendAction, { text: text }))
                            text = ""
                        }
                    }

                    MeoIconButton {
                        icon.name: parent.composer.busy ? "stop" : "arrow_upward"
                        onClicked: parent.composer.busy ? window.act(parent.composer.stopAction) : input.send()
                    }
                }
            }
        }
    }
}

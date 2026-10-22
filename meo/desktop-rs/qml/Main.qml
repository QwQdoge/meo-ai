// Generic renderer for the Meo AI core view (meo_ai_core::cloud::app).
// It knows only component kinds, never product features: navigation entries,
// pages, settings and buttons all come from `core.view`. Every interaction
// sends the action object attached to the element back to the core.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
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

    // Tell the core whether the window is in front, so it only notifies from the background.
    onActiveChanged: core.dispatch(JSON.stringify({ type: "set_foreground", visible: active }))

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
        supportingContent: spec && spec.input ? (spec.input.multiline ? promptArea : promptField) : null
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

    Component {
        id: promptArea
        MeoTextArea {
            width: 320
            height: 120
            placeholder: appDialog.spec && appDialog.spec.input ? appDialog.spec.input.placeholder : ""
            text: appDialog.inputValue
            onTextChanged: appDialog.inputValue = text
            Component.onCompleted: forceActiveFocus()
        }
    }

    // File picker for attachments; the core reads the chosen file itself.
    FileDialog {
        id: attachDialog
        property string actionType: "attach_path"
        nameFilters: [qsTr("Text, code and pictures (*.png *.jpg *.jpeg *.webp *.gif *.txt *.md *.markdown *.csv *.json *.py *.rs *.js *.ts *.tsx *.jsx *.java *.kt *.c *.h *.cpp *.go *.sh *.toml *.yaml *.yml *.html *.css *.sql *.log)"), qsTr("All files (*)")]
        onAccepted: window.act({ type: "attach_path", path: selectedFile.toString() })
    }

    // QML has no direct clipboard API: select and copy from an invisible field.
    TextEdit { id: clipboardHelper; visible: false }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // Claude-style left column from `view.sidebar`: Chat | Work, search, new chat, plugins,
        // projects tree and chats; collapses to an icon rail.
        ColumnLayout {
            id: sidebar
            visible: !!window.v.sidebar
            readonly property var sb: window.v.sidebar || ({})
            readonly property bool collapsed: !!sb.collapsed
            readonly property var rows: {
                const out = []
                const symbol = icon => icon === "skills" ? "extension" : icon === "projects" ? "folder" : icon === "work" ? "work" : icon === "settings" ? "settings" : "chat"
                for (const sec of (sb.sections || [])) {
                    if (sec.kind === "list") {
                        if (collapsed) continue
                        out.push({ kind: "header", label: sec.label, tabs: sec.tabs || [] })
                        for (const item of (sec.items || [])) out.push({ kind: "item", depth: 0, data: item })
                    } else {
                        out.push({ kind: "link", label: sec.label, symbol: symbol(sec.icon), selected: !!sec.selected, action: sec.action })
                        if (sec.kind === "tree" && !collapsed)
                            for (const p of (sec.items || [])) {
                                out.push({ kind: "item", depth: 1, data: p })
                                for (const c of (p.children || [])) out.push({ kind: "item", depth: 2, data: c })
                            }
                    }
                }
                return out
            }
            Layout.preferredWidth: collapsed ? 56 : 232
            Layout.fillHeight: true
            Layout.margins: 12
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                MeoSegmentedButtons {
                    visible: !sidebar.collapsed
                    Layout.fillWidth: true
                    size: "xs"
                    model: (sidebar.sb.modes || []).map(m => m.label)
                    currentIndex: Math.max(0, (sidebar.sb.modes || []).findIndex(m => m.selected))
                    onSelected: (index, data) => window.act(sidebar.sb.modes[index].action)
                }
                MeoIconButton {
                    type: "standard"
                    icon.name: sidebar.collapsed ? "chevron_right" : "chevron_left"
                    onClicked: window.act(sidebar.sb.toggle)
                }
            }
            Repeater {
                model: sidebar.collapsed ? (sidebar.sb.modes || []) : []
                MeoIconButton {
                    required property var modelData
                    Layout.alignment: Qt.AlignHCenter
                    type: modelData.selected ? "tonal" : "standard"
                    icon.name: modelData.icon === "work" ? "work" : "chat"
                    onClicked: window.act(modelData.action)
                }
            }
            MeoTextField {
                id: searchField
                visible: !sidebar.collapsed && !!sidebar.sb.search
                Layout.fillWidth: true
                placeholder: (sidebar.sb.search || {}).placeholder || ""
                leadingIcon: "search"
                // Typed text wins; the core echoes it back as the saved value.
                onTextChanged: if (text !== (sidebar.sb.search || {}).value) searchTimer.restart()
                Timer {
                    id: searchTimer
                    interval: 300
                    onTriggered: window.act(window.withFields(sidebar.sb.search.action, { text: searchField.text }))
                }
            }
            MeoButton {
                Layout.fillWidth: true
                visible: !!sidebar.sb.newChat
                type: "text"
                size: "xs"
                text: sidebar.collapsed ? "+" : "+  " + ((sidebar.sb.newChat || {}).label || "")
                onClicked: window.act((sidebar.sb.newChat || {}).action)
            }
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 2
                model: sidebar.rows
                delegate: Item {
                    id: sideRow
                    required property var modelData
                    width: ListView.view.width
                    implicitHeight: modelData.kind === "item" ? itemRow.implicitHeight : modelData.kind === "header" ? headerCol.implicitHeight : linkButton.implicitHeight
                    height: implicitHeight
                    MeoListItem {
                        id: linkButton
                        visible: sideRow.modelData.kind === "link"
                        width: parent.width
                        isDense: true
                        headline: sidebar.collapsed ? "" : (sideRow.modelData.label || "")
                        leadingIcon: sideRow.modelData.symbol || ""
                        selected: !!sideRow.modelData.selected
                        onClicked: window.act(sideRow.modelData.action)
                    }
                    ColumnLayout {
                        id: headerCol
                        visible: sideRow.modelData.kind === "header"
                        width: parent.width
                        spacing: 4
                        MeoText { text: sideRow.modelData.label || ""; typeRole: "label"; color: MeoTheme.onSurfaceVariant }
                        RowLayout {
                            spacing: 8
                            Repeater {
                                model: sideRow.modelData.tabs || []
                                MeoButton {
                                    required property var modelData
                                    text: modelData.label
                                    type: modelData.selected ? "tonal" : "outlined"
                                    size: "xs"
                                    onClicked: window.act(modelData.action)
                                }
                            }
                        }
                    }
                    Item {
                        id: itemRow
                        visible: sideRow.modelData.kind === "item"
                        width: parent.width
                        implicitHeight: row.implicitHeight
                        MeoListItem {
                            id: row
                            x: ((sideRow.modelData.depth || 0) > 0 ? (sideRow.modelData.depth - 1) * 16 : 0)
                            width: parent.width - x
                            headline: (sideRow.modelData.data || {}).title || ""
                            isDense: true
                            selected: !!(sideRow.modelData.data || {}).selected
                            onClicked: window.act(sideRow.modelData.data.action)
                        }
                        MeoIconButton {
                            visible: ((sideRow.modelData.data || {}).menu || []).length > 0
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
                                model: (sideRow.modelData.data || {}).menu || []
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
            Repeater {
                model: sidebar.sb.footer || []
                MeoListItem {
                    required property var modelData
                    Layout.fillWidth: true
                    isDense: true
                    headline: sidebar.collapsed ? "" : modelData.label
                    leadingIcon: "settings"
                    selected: !!modelData.selected
                    onClicked: window.act(modelData.action)
                }
            }
        }

        Rectangle { visible: !!window.v.sidebar; Layout.fillHeight: true; width: 1; color: MeoTheme.outlineVariant }

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
                confirmText: (window.v.strings || {}).dismiss || qsTr("Dismiss")
                onConfirmed: window.act(window.v.notice.action)
            }

            MeoBanner {
                visible: window.v.online === false
                Layout.fillWidth: true
                Layout.margins: 12
                tone: "warning"
                icon: "cloud_off"
                text: (window.v.strings || {}).offline || qsTr("Offline — showing saved data")
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

    // Settings: one large card, categories on the left, one page on the right.
    Component {
        id: settingsPage
        Item {
            readonly property var sections: window.page.sections || []
            readonly property var current: sections.find(x => x.id === window.page.selected) || sections[0] || ({ items: [] })
            readonly property var navRows: {
                const out = []
                for (const g of (window.page.nav || [])) {
                    out.push({ header: g.label })
                    for (const e of g.items) out.push({ entry: e })
                }
                return out
            }
            Rectangle {
                anchors.fill: parent
                anchors.margins: 16
                radius: 22
                color: MeoTheme.surface
                border.color: MeoTheme.outlineVariant
                RowLayout {
                    anchors.fill: parent
                    spacing: 0
                    ListView {
                        Layout.preferredWidth: 210
                        Layout.fillHeight: true
                        Layout.margins: 8
                        clip: true
                        spacing: 2
                        model: navRows
                        delegate: Item {
                            required property var modelData
                            width: ListView.view.width
                            height: modelData.header ? 28 : 36
                            MeoText { visible: !!modelData.header; text: modelData.header || ""; typeRole: "label"; color: MeoTheme.onSurfaceVariant; anchors.bottom: parent.bottom; x: 10 }
                            MeoListItem {
                                visible: !!modelData.entry
                                anchors.fill: parent
                                isDense: true
                                headline: modelData.entry ? modelData.entry.label : ""
                                selected: modelData.entry ? !!modelData.entry.selected : false
                                onClicked: window.act(modelData.entry.action)
                            }
                        }
                    }
                    Rectangle { Layout.fillHeight: true; width: 1; color: MeoTheme.outlineVariant }
                    Flickable {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        contentHeight: settingsColumn.implicitHeight + 48
                        clip: true
                        ColumnLayout {
                            id: settingsColumn
                            x: 28
                            y: 20
                            width: Math.min(parent.width - 56, 680)
                            spacing: 16
                            RowLayout {
                                Layout.fillWidth: true
                                MeoText { text: current.label || window.page.title || ""; typeRole: "title"; typeSize: "big"; Layout.fillWidth: true }
                                MeoIconButton { visible: !!window.page.close; type: "standard"; icon.name: "close"; onClicked: window.act(window.page.close) }
                            }
                            Repeater {
                                model: current.items || []
                                SettingControl { required property var modelData; item: modelData; Layout.fillWidth: true }
                            }
                        }
                    }
                }
            }
        }
    }

    component ControlChip: Item {
        id: chipRoot
        property var item: ({})
        readonly property var options: item.options || []
        readonly property int index: Math.max(0, options.findIndex(o => o.value === item.value))
        implicitWidth: chip.implicitWidth
        implicitHeight: chip.implicitHeight
        function choose(value) { window.act({ type: "set_setting", binding: item.binding, value: value }) }
        MeoButton {
            id: chip
            type: "text"
            size: "xs"
            text: item.kind === "toggle" ? ((item.value === true ? "● " : "○ ") + (item.label || ""))
                                          : (((options[index] || {}).label || item.label || "") + " ▾")
            onClicked: item.kind === "toggle" ? chipRoot.choose(item.value !== true)
                       : item.kind === "select" ? selectMenu.popup() : sliderPopup.open()
        }
        Menu {
            id: selectMenu
            Repeater {
                model: chipRoot.item.kind === "select" ? chipRoot.options : []
                MenuItem { required property var modelData; text: modelData.label; onTriggered: chipRoot.choose(modelData.value) }
            }
        }
        Popup {
            id: sliderPopup
            y: -height - 4
            padding: 12
            ColumnLayout {
                spacing: 4
                MeoText { text: (chipRoot.item.label || "") + " · " + ((chipRoot.options[chipRoot.index] || {}).label || ""); typeRole: "label"; color: MeoTheme.onSurfaceVariant }
                MeoSlider {
                    Layout.preferredWidth: 160
                    from: 0
                    to: Math.max(1, chipRoot.options.length - 1)
                    stepSize: 1
                    discrete: true
                    value: chipRoot.index
                    onMoved: v => chipRoot.choose(chipRoot.options[Math.round(v)].value)
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
        ColumnLayout {
            visible: item.kind === "slider"
            spacing: 0
            readonly property int index: Math.max(0, (item.options || []).findIndex(o => o.value === item.value))
            MeoText {
                text: (item.label || "") + " · " + (((item.options || [])[parent.index] || {}).label || "")
                typeRole: "label"
                color: MeoTheme.onSurfaceVariant
            }
            MeoSlider {
                Layout.preferredWidth: 110
                from: 0
                to: Math.max(1, (item.options || []).length - 1)
                stepSize: 1
                discrete: true
                value: parent.index
                onMoved: v => window.act({ type: "set_setting", binding: item.binding, value: item.options[Math.round(v)].value })
            }
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
        Rectangle {
            visible: item.kind === "stats"
            Layout.fillWidth: true
            implicitHeight: 64
            radius: 18
            color: "transparent"
            border.color: MeoTheme.outlineVariant
            RowLayout {
                anchors.fill: parent
                spacing: 0
                Repeater {
                    model: item.kind === "stats" ? (item.items || []) : []
                    ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        spacing: 0
                        MeoText { text: modelData.value; typeRole: "title"; typeSize: "small"; Layout.alignment: Qt.AlignHCenter }
                        MeoText { text: modelData.label; typeRole: "label"; color: MeoTheme.onSurfaceVariant; Layout.alignment: Qt.AlignHCenter }
                    }
                }
            }
        }
        ColumnLayout {
            visible: item.kind === "bars"
            Layout.fillWidth: true
            spacing: 6
            readonly property real peak: Math.max(1, ...((item.items || []).map(b => b.value)))
            MeoText { text: item.label || ""; typeRole: "label"; color: MeoTheme.onSurfaceVariant }
            Row {
                Layout.fillWidth: true
                height: 72
                spacing: 3
                Repeater {
                    model: item.kind === "bars" ? (item.items || []) : []
                    Item {
                        required property var modelData
                        width: Math.max(3, (parent.width - 3 * ((item.items || []).length - 1)) / Math.max(1, (item.items || []).length))
                        height: 72
                        Rectangle {
                            anchors.bottom: parent.bottom
                            width: parent.width
                            height: Math.max(3, parent.height * modelData.value / parent.parent.parent.peak)
                            radius: 3
                            color: MeoTheme.primary
                            opacity: 0.75
                        }
                    }
                }
            }
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
        RowLayout {
            visible: item.kind === "item"
            Layout.fillWidth: true
            spacing: 12
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                MeoText { text: item.label || ""; wrapMode: Text.Wrap; Layout.fillWidth: true }
                MeoText {
                    visible: !!item.value
                    text: String(item.value || "")
                    color: MeoTheme.onSurfaceVariant
                    typeRole: "label"
                    Layout.fillWidth: true
                }
            }
            Repeater {
                model: item.buttons || []
                ActionButton { spec: modelData }
            }
        }
    }

    Component {
        id: conversationPage
        RowLayout {
            spacing: 0

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

                    Flow {
                        visible: !!window.page.empty && commandList.matches.length === 0
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.top: parent.verticalCenter
                        anchors.topMargin: 90
                        width: Math.min(parent.width - 64, 560)
                        spacing: 8
                        Repeater {
                            model: window.page.empty ? (window.page.empty.suggestions || []) : []
                            MeoButton {
                                required property var modelData
                                text: modelData.label
                                type: "tonal"
                                onClicked: window.act(modelData.action)
                            }
                        }
                    }

                    Rectangle {
                        id: inspectorCard
                        readonly property var info: window.page.inspector || ({})
                        visible: !!info.visible
                        z: 2
                        anchors.top: parent.top
                        anchors.right: parent.right
                        anchors.margins: 16
                        width: 210
                        height: inspectorColumn.implicitHeight + 24
                        radius: 16
                        color: MeoTheme.surfaceContainer
                        border.color: MeoTheme.outlineVariant
                        ColumnLayout {
                            id: inspectorColumn
                            x: 12
                            y: 12
                            width: parent.width - 24
                            spacing: 4
                            RowLayout {
                                Layout.fillWidth: true
                                MeoText { text: inspectorCard.info.title || ""; typeRole: "label"; Layout.fillWidth: true }
                                MeoIconButton { type: "standard"; size: "xs"; icon.name: "close"; onClicked: window.act(inspectorCard.info.hide) }
                            }
                            Repeater {
                                model: (inspectorCard.info.rows || []).filter(r => r.value !== null)
                                RowLayout {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    MeoText { text: modelData.label; typeRole: "label"; color: MeoTheme.onSurfaceVariant; Layout.fillWidth: true }
                                    MeoText { text: String(modelData.value); typeRole: "label"; horizontalAlignment: Text.AlignRight; elide: Text.ElideRight; Layout.maximumWidth: 130 }
                                }
                            }
                            Repeater {
                                model: inspectorCard.info.resources || []
                                MeoText {
                                    required property var modelData
                                    text: modelData.title || modelData.url || ""
                                    typeRole: "label"
                                    color: MeoTheme.primary
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: if (/^https?:\/\//.test(modelData.url || "")) Qt.openUrlExternally(modelData.url)
                                    }
                                }
                            }
                        }
                    }
                    MeoButton {
                        visible: !!(window.page.inspector || {}).title && !(window.page.inspector || {}).visible
                        anchors.top: parent.top
                        anchors.right: parent.right
                        anchors.margins: 16
                        type: "tonal"
                        size: "xs"
                        text: (window.page.inspector || {}).title || ""
                        onClicked: window.act(window.page.inspector.show)
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
                            implicitHeight: stepsBox.height + bubble.implicitHeight + pictures.height + (messageActions.visible ? messageActions.implicitHeight + 4 : 0)
                            readonly property bool mine: modelData.role === "user"
                            // Steps of the answer (search, model, ...): collapsed once it is done.
                            Column {
                                id: stepsBox
                                visible: !!modelData.steps
                                width: parent.width
                                height: visible ? implicitHeight : 0
                                spacing: 2
                                property bool toggled: false
                                property bool manual: false
                                readonly property bool open: toggled ? manual : !!modelData.stepsOpen
                                MeoButton {
                                    text: (stepsBox.open ? "▾ " : "▸ ") + (modelData.stepsLabel || "")
                                    type: "text"
                                    size: "xs"
                                    onClicked: { stepsBox.manual = !stepsBox.open; stepsBox.toggled = true }
                                }
                                Repeater {
                                    model: stepsBox.open ? (modelData.steps || []) : []
                                    Column {
                                        required property var modelData
                                        x: 16
                                        width: stepsBox.width - 32
                                        Text {
                                            width: parent.width
                                            wrapMode: Text.Wrap
                                            color: MeoTheme.onSurfaceVariant
                                            font.pixelSize: 13
                                            text: (modelData.status === "done" ? "✓ " : modelData.status === "error" ? "✕ " : "… ") + modelData.title + (modelData.detail ? " — " + modelData.detail : "")
                                        }
                                        Repeater {
                                            model: modelData.items || []
                                            Text {
                                                required property var modelData
                                                x: 16
                                                width: parent.width - 16
                                                elide: Text.ElideRight
                                                color: MeoTheme.primary
                                                font.pixelSize: 12
                                                text: modelData.title || modelData.url
                                                MouseArea {
                                                    anchors.fill: parent
                                                    cursorShape: Qt.PointingHandCursor
                                                    onClicked: if (/^https?:\/\//.test(modelData.url)) Qt.openUrlExternally(modelData.url)
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            // Images created by the model (urls or data urls).
                            Column {
                                id: pictures
                                y: stepsBox.height + bubble.implicitHeight + 4
                                spacing: 8
                                Repeater {
                                    model: modelData.images || []
                                    Image {
                                        required property var modelData
                                        source: modelData.url
                                        width: Math.min(512, messages.width - 32)
                                        fillMode: Image.PreserveAspectFit
                                        asynchronous: true
                                    }
                                }
                            }
                            Row {
                                id: messageActions
                                visible: !modelData.streaming && !!modelData.text
                                y: stepsBox.height + bubble.implicitHeight + pictures.height + 4
                                anchors.right: parent.mine ? parent.right : undefined
                                spacing: 4
                                MeoButton {
                                    text: (window.v.strings || {}).copy || qsTr("Copy")
                                    type: "text"
                                    size: "xs"
                                    onClicked: {
                                        clipboardHelper.text = modelData.text
                                        clipboardHelper.selectAll()
                                        clipboardHelper.copy()
                                    }
                                }
                                Repeater {
                                    model: modelData.actions || []
                                    MeoButton {
                                        required property var modelData
                                        text: modelData.label
                                        type: "text"
                                        size: "xs"
                                        onClicked: window.act(modelData.action)
                                    }
                                }
                            }
                            Rectangle {
                                id: bubble
                                y: stepsBox.height
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

                Flow {
                    visible: (window.page.files || []).length > 0
                    Layout.fillWidth: true
                    Layout.leftMargin: 16
                    Layout.rightMargin: 16
                    spacing: 6
                    Repeater {
                        model: window.page.files || []
                        MeoButton {
                            required property var modelData
                            text: modelData.name + "  ✕"
                            type: "tonal"
                            size: "xs"
                            onClicked: window.act(modelData.remove.action)
                        }
                    }
                }

                Column {
                    id: commandList
                    readonly property var matches: /^\/\S*$/.test(input.text)
                        ? (window.page.composer.commands || []).filter(c => c.name.indexOf(input.text.toLowerCase()) === 0) : []
                    visible: matches.length > 0
                    Layout.leftMargin: 16
                    Layout.rightMargin: 16
                    Repeater {
                        model: commandList.matches
                        MeoButton {
                            required property var modelData
                            text: modelData.name + (modelData.hint ? " " + modelData.hint : "") + " — " + modelData.label
                            type: "text"
                            size: "xs"
                            onClicked: {
                                if (modelData.hint) { input.text = modelData.name + " "; input.forceActiveFocus() }
                                else if (!window.page.composer.busy) {
                                    window.act(window.withFields(window.page.composer.sendAction, { text: modelData.name }))
                                    input.text = ""
                                }
                            }
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.margins: 16
                    spacing: 8
                    readonly property var composer: window.page.composer || ({})

                    MeoIconButton {
                        visible: !!parent.composer.attach
                        Layout.alignment: Qt.AlignBottom
                        type: "standard"
                        icon.name: "attach_file"
                        onClicked: attachDialog.open()
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

                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 16
                    Layout.rightMargin: 16
                    Layout.bottomMargin: 8
                    spacing: 4
                    readonly property var items: (window.page.composer || {}).toolbar || []
                    Repeater {
                        model: parent.items.filter(i => i.align !== "end")
                        ControlChip { required property var modelData; item: modelData }
                    }
                    Item { Layout.fillWidth: true }
                    Repeater {
                        model: parent.items.filter(i => i.align === "end")
                        ControlChip { required property var modelData; item: modelData }
                    }
                }
            }
        }
    }
}

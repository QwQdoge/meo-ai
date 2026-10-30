// Generic renderer for the Meo AI core view (meo_ai_core::cloud::app).
// It knows only component kinds, never product features: navigation entries,
// pages, settings and buttons all come from `core.view`. Every interaction
// sends the action object attached to the element back to the core.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Shapes
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
        if (action && action.type === "open_link") {
            if (/^https:\/\//.test(action.url || "")) Qt.openUrlExternally(action.url)
            return
        }
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
            echoMode: appDialog.spec && appDialog.spec.input && appDialog.spec.input.secret ? TextInput.Password : TextInput.Normal
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

    // Wallpaper-derived Material colors and light/dark mode from the Meo desktop, when present.
    Loader { source: "DynamicColors.qml" }

    // One sidebar row (Plugins, Projects, Settings): the icon and the label share one vertical centre.
    component SideLink: Rectangle {
        id: link
        property string symbol: ""
        property string label: ""
        property bool selected: false
        property bool compact: false
        signal clicked()
        implicitHeight: 36
        radius: 10
        color: selected ? MeoTheme.secondaryContainer
                        : (linkHover.hovered ? MeoTheme.surfaceContainerHigh : "transparent")
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            spacing: 12
            MeoIcon {
                icon: link.symbol
                size: 20
                color: link.selected ? MeoTheme.contentOnSecondaryContainer : MeoTheme.onSurfaceVariant
                Layout.alignment: Qt.AlignVCenter
                verticalAlignment: Text.AlignVCenter
            }
            MeoText {
                visible: !link.compact
                text: link.label
                elide: Text.ElideRight
                font.weight: link.selected ? Font.DemiBold : Font.Normal
                verticalAlignment: Text.AlignVCenter
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
            }
        }
        HoverHandler { id: linkHover }
        TapHandler { onTapped: link.clicked() }
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
            Layout.preferredWidth: collapsed ? 52 : 224
            Layout.minimumWidth: Layout.preferredWidth
            Layout.maximumWidth: Layout.preferredWidth
            Layout.fillHeight: true
            Layout.margins: 8
            spacing: 4

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
            Rectangle {
                id: searchPill
                visible: !sidebar.collapsed && !!sidebar.sb.search
                Layout.fillWidth: true
                implicitHeight: 34
                radius: height / 2
                color: MeoTheme.surfaceContainerHigh
                border.width: 1
                border.color: searchField.activeFocus ? MeoTheme.primary : "transparent"
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    spacing: 8
                    MeoIcon { icon: "search"; size: 18; color: MeoTheme.onSurfaceVariant }
                    TextInput {
                        id: searchField
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        clip: true
                        font.pixelSize: 14
                        color: MeoTheme.onSurface
                        selectByMouse: true
                        text: ""
                        // Typed text wins; the core echoes it back as the saved value.
                        onTextChanged: if (text !== (sidebar.sb.search || {}).value) searchTimer.restart()
                        Text {
                            visible: !parent.text && !parent.activeFocus
                            text: (sidebar.sb.search || {}).placeholder || ""
                            color: MeoTheme.onSurfaceVariant
                            font.pixelSize: 14
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Timer {
                            id: searchTimer
                            interval: 300
                            onTriggered: window.act(window.withFields(sidebar.sb.search.action, { text: searchField.text }))
                        }
                    }
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
                spacing: 0
                model: sidebar.rows
                delegate: Item {
                    id: sideRow
                    required property var modelData
                    width: ListView.view.width
                    implicitHeight: modelData.kind === "item" ? itemRow.implicitHeight : modelData.kind === "header" ? headerCol.implicitHeight : linkButton.implicitHeight
                    height: implicitHeight
                    SideLink {
                        id: linkButton
                        visible: sideRow.modelData.kind === "link"
                        width: parent.width
                        symbol: sideRow.modelData.symbol || ""
                        label: sideRow.modelData.label || ""
                        compact: sidebar.collapsed
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
                        HoverHandler { id: rowHover }
                        MeoIconButton {
                            visible: ((sideRow.modelData.data || {}).menu || []).length > 0 && (rowHover.hovered || chatMenu.visible)
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
            RowLayout {
                Layout.fillWidth: true
                spacing: 4
                Repeater {
                    model: sidebar.sb.footer || []
                    SideLink {
                        required property var modelData
                        Layout.fillWidth: true
                        symbol: "settings"
                        label: modelData.label
                        compact: sidebar.collapsed
                        selected: !!modelData.selected
                        onClicked: window.act(modelData.action)
                    }
                }
                // Online / live-sync state at a glance.
                Rectangle {
                    visible: !!sidebar.sb.status
                    Layout.preferredWidth: 10
                    Layout.preferredHeight: 10
                    Layout.rightMargin: 8
                    radius: 5
                    color: (sidebar.sb.status || {}).kind === "live" ? MeoTheme.success
                         : (sidebar.sb.status || {}).kind === "offline" ? MeoTheme.error : MeoTheme.outline
                    ToolTip.visible: statusHover.hovered
                    ToolTip.text: (sidebar.sb.status || {}).label || ""
                    HoverHandler { id: statusHover }
                }
            }
        }

        Rectangle { visible: !!window.v.sidebar; Layout.fillHeight: true; width: 1; color: MeoTheme.outlineVariant }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            // The page decides its own width; a wide child must never squeeze the sidebar.
            Layout.minimumWidth: 0
            Layout.preferredWidth: 0
            spacing: 0

            MeoBanner {
                visible: !!window.v.notice
                Layout.fillWidth: true
                Layout.margins: 12
                tone: window.v.notice && window.v.notice.kind === "error" ? "error" : "tonal"
                text: window.v.notice ? window.v.notice.text : ""
                confirmText: (window.v.notice && window.v.notice.actionLabel) || (window.v.strings || {}).dismiss || qsTr("Dismiss")
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
                    store: storePage,
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
                MeoText { text: window.page.title || ""; typeRole: "title"; typeSize: "medium"; Layout.fillWidth: true }
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

    // Plugin store: tabs, search, category chips, app cards and import forms from the core.
    component AppIcon: Rectangle {
        id: appIcon
        property var icon: null
        property string label: ""
        property real tile: 44
        width: tile; height: tile; radius: tile * 0.28
        readonly property bool hasSvg: !!(icon && icon.svg)
        readonly property bool hasGlyph: !!(icon && icon.glyph)
        readonly property color brand: (icon && icon.color) ? icon.color : MeoTheme.contentOnSurface
        color: (hasSvg || hasGlyph) ? MeoTheme.surfaceContainerHighest : Qt.hsla(((label.charCodeAt(0) || 0) * 37 % 360) / 360, 0.55, 0.42, 1)
        Shape {
            visible: appIcon.hasSvg
            anchors.centerIn: parent
            width: 24; height: 24
            scale: appIcon.tile * 0.56 / 24
            ShapePath {
                fillColor: appIcon.brand
                strokeColor: "transparent"
                PathSvg { path: appIcon.hasSvg ? appIcon.icon.svg : "" }
            }
        }
        MeoIcon {
            visible: appIcon.hasGlyph
            anchors.centerIn: parent
            icon: appIcon.hasGlyph ? appIcon.icon.glyph : ""
            size: appIcon.tile * 0.5
            color: appIcon.brand
        }
        MeoText {
            visible: !appIcon.hasSvg && !appIcon.hasGlyph
            anchors.centerIn: parent
            text: (appIcon.label.match(/[A-Za-z0-9\u00C0-\uFFFF]/) || ["?"])[0].toUpperCase()
            color: "white"
            typeRole: "title"; typeSize: "medium"
        }
    }

    Component {
        id: storePage
        Flickable {
            id: storeFlick
            contentWidth: width
            contentHeight: storeCol.implicitHeight + 48
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            property string query: window.page.search ? (window.page.search.value || "") : ""
            ColumnLayout {
                id: storeCol
                x: 24; y: 24
                width: storeFlick.width - 48
                spacing: 14
                RowLayout {
                    Layout.fillWidth: true
                    MeoText { text: window.page.title || ""; typeRole: "title"; typeSize: "large"; Layout.fillWidth: true }
                    MeoLoadingIndicator { visible: !!window.page.loading }
                }
                MeoTextField {
                    Layout.fillWidth: true
                    Layout.maximumWidth: 640
                    placeholder: window.page.search ? window.page.search.placeholder : ""
                    text: storeFlick.query
                    onAccepted: window.act(window.withFields(window.page.search.action, ({ query: text })))
                }
                MeoSegmentedButtons {
                    Layout.preferredWidth: 360
                    size: "s"
                    model: (window.page.tabs || []).map(t => t.label)
                    currentIndex: Math.max(0, (window.page.tabs || []).findIndex(t => t.selected))
                    onSelected: (index, data) => window.act(window.page.tabs[index].action)
                }
                MeoSegmentedButtons {
                    visible: (window.page.filters || []).length > 0
                    Layout.preferredWidth: 360
                    size: "xs"
                    model: (window.page.filters || []).map(f => f.label)
                    currentIndex: Math.max(0, (window.page.filters || []).findIndex(f => f.selected))
                    onSelected: (index, data) => window.act(window.page.filters[index].action)
                }
                Repeater {
                    model: window.page.sections || []
                    delegate: ColumnLayout {
                        id: sectionCol
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 10
                        MeoText { text: sectionCol.modelData.title || ""; typeRole: "title"; typeSize: "small" }
                        MeoText {
                            visible: !!sectionCol.modelData.cards && sectionCol.modelData.cards.length === 0 && !!sectionCol.modelData.empty
                            text: sectionCol.modelData.empty || ""
                            color: MeoTheme.onSurfaceVariant
                        }
                        Flow {
                            Layout.fillWidth: true
                            spacing: 12
                            Repeater {
                                model: sectionCol.modelData.cards || []
                                delegate: Rectangle {
                                    id: card
                                    required property var modelData
                                    readonly property int columns: Math.max(1, Math.floor((storeCol.width + 12) / 340))
                                    width: (storeCol.width - 12 * (columns - 1)) / columns
                                    height: cardCol.implicitHeight + 28
                                    radius: 20
                                    color: MeoTheme.surfaceContainerLow
                                    RowLayout {
                                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 14 }
                                        spacing: 12
                                        AppIcon { icon: card.modelData.icon; label: card.modelData.title || ""; Layout.alignment: Qt.AlignTop }
                                        ColumnLayout {
                                            id: cardCol
                                            Layout.fillWidth: true
                                            spacing: 4
                                            MeoText { text: card.modelData.title || ""; typeRole: "title"; typeSize: "small"; Layout.fillWidth: true; wrapMode: Text.Wrap }
                                            MeoText { text: card.modelData.publisher || ""; color: MeoTheme.onSurfaceVariant; Layout.fillWidth: true; elide: Text.ElideRight }
                                            MeoText { text: card.modelData.subtitle || ""; Layout.fillWidth: true; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight }
                                            MeoText {
                                                text: (card.modelData.badges || []).concat(card.modelData.state === "installed" ? ["✓ Installed"] : []).join("  ·  ")
                                                color: MeoTheme.primary
                                            }
                                            RowLayout {
                                                visible: (card.modelData.actions || []).length > 0
                                                Layout.alignment: Qt.AlignRight
                                                Repeater { model: card.modelData.actions || []; ActionButton { spec: modelData } }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        Repeater {
                            model: sectionCol.modelData.forms || []
                            delegate: Rectangle {
                                id: form
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.maximumWidth: 720
                                implicitHeight: formCol.implicitHeight + 28
                                radius: 20
                                color: MeoTheme.surfaceContainerLow
                                ColumnLayout {
                                    id: formCol
                                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 14 }
                                    spacing: 8
                                    RowLayout {
                                        spacing: 10
                                        AppIcon { icon: form.modelData.icon; label: form.modelData.title || ""; tile: 36 }
                                        MeoText { text: form.modelData.title || ""; typeRole: "title"; typeSize: "small" }
                                    }
                                    MeoText { text: form.modelData.text || ""; color: MeoTheme.onSurfaceVariant; Layout.fillWidth: true; wrapMode: Text.Wrap }
                                    MeoTextField {
                                        id: formInput
                                        Layout.fillWidth: true
                                        placeholder: form.modelData.placeholder || ""
                                        onAccepted: form.submit()
                                    }
                                    MeoButton {
                                        text: form.modelData.button || ""
                                        type: "filled"
                                        enabled: formInput.text.trim().length > 0
                                        onClicked: form.submit()
                                    }
                                }
                                function submit() {
                                    const value = formInput.text.trim()
                                    if (!value) return
                                    const fields = ({})
                                    fields[modelData.field] = value
                                    window.act(window.withFields(modelData.action, fields))
                                    formInput.text = ""
                                }
                            }
                        }
                        Repeater {
                            model: sectionCol.modelData.links || []
                            delegate: MeoListItem {
                                required property var modelData
                                Layout.fillWidth: true
                                headline: modelData.title || ""
                                supportingText: modelData.subtitle || ""
                                interactive: true
                                onClicked: if (/^https:\/\//.test(modelData.url || "")) Qt.openUrlExternally(modelData.url)
                            }
                        }
                    }
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
                                MeoText { text: current.label || window.page.title || ""; typeRole: "title"; typeSize: "medium"; Layout.fillWidth: true }
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
        implicitWidth: iconChip.visible ? iconChip.implicitWidth : chip.implicitWidth
        implicitHeight: iconChip.visible ? iconChip.implicitHeight : chip.implicitHeight
        function choose(value) { window.act({ type: "set_setting", binding: item.binding, value: value }) }
        // Toggles with an icon are icon-only (tooltip carries the name); the rest keep a short text.
        MeoIconButton {
            id: iconChip
            visible: item.kind === "toggle" && !!item.icon
            type: item.value === true ? "tonal" : "standard"
            size: "xs"
            icon.name: item.icon || ""
            ToolTip.visible: hovered
            ToolTip.text: item.label || ""
            onClicked: chipRoot.choose(item.value !== true)
        }
        MeoButton {
            id: chip
            visible: !iconChip.visible
            type: "text"
            size: "xs"
            icon.name: (item.kind !== "toggle" && item.icon) ? item.icon : ""
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
        MeoText {
            visible: item.kind === "hint"
            Layout.fillWidth: true
            text: item.text || ""
            wrapMode: Text.Wrap
            typeRole: "label"
            color: MeoTheme.onSurfaceVariant
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
                id: chatColumn
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0

                RowLayout {
                    Layout.fillWidth: true
                    Layout.margins: 10
                    spacing: 4
                    MeoText {
                        text: window.page.title || ""
                        typeRole: "title"
                        typeSize: "small"
                        elide: Text.ElideRight
                        Layout.maximumWidth: parent.width - 80
                    }
                    MeoIconButton {
                        visible: (window.page.menu || []).length > 0
                        type: "standard"
                        size: "xs"
                        icon.name: "more_horiz"
                        onClicked: pageMenu.popup()
                        Menu {
                            id: pageMenu
                            Repeater {
                                model: window.page.menu || []
                                MenuItem {
                                    required property var modelData
                                    text: modelData.label
                                    onTriggered: window.act(modelData.action)
                                }
                            }
                        }
                    }
                    Item { Layout.fillWidth: true }
                }

                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    MeoEmptyState {
                        visible: !!window.page.empty
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.verticalCenterOffset: -110
                        icon: "chat"
                        title: window.page.empty ? window.page.empty.title : ""
                        description: window.page.empty ? window.page.empty.text : ""
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
                                model: inspectorCard.info.sections || []
                                Column {
                                    id: sec
                                    required property var modelData
                                    property bool open: modelData.open !== false
                                    Layout.fillWidth: true
                                    spacing: 3
                                    MeoButton {
                                        text: (sec.open ? "▾ " : "▸ ") + (modelData.title || "")
                                        type: "text"
                                        size: "xs"
                                        onClicked: sec.open = !sec.open
                                    }
                                    Row {
                                        visible: sec.open && !!modelData.bar
                                        width: parent.width
                                        height: 6
                                        spacing: 1
                                        Repeater {
                                            model: (modelData.bar || {}).segments || []
                                            Rectangle {
                                                required property var modelData
                                                required property int index
                                                readonly property real sum: Math.max(1, ((sec.modelData.bar || {}).segments || []).reduce((n, x) => n + x.value, 0))
                                                width: Math.max(2, (sec.width - 3) * modelData.value / sum)
                                                height: 6
                                                radius: 3
                                                color: index === 0 ? MeoTheme.primary : index === 1 ? MeoTheme.tertiary : MeoTheme.outlineVariant
                                            }
                                        }
                                    }
                                    MeoText {
                                        visible: sec.open && !!(modelData.bar || {}).label
                                        text: (modelData.bar || {}).label || ""
                                        typeRole: "label"
                                        color: MeoTheme.onSurfaceVariant
                                    }
                                    Repeater {
                                        model: sec.open ? (modelData.rows || []).filter(r => r.label) : []
                                        RowLayout {
                                            required property var modelData
                                            width: sec.width
                                            Rectangle {
                                                visible: !!modelData.status
                                                width: 6; height: 6; radius: 3
                                                color: modelData.status === "error" ? MeoTheme.error : modelData.status === "done" ? MeoTheme.primary : MeoTheme.outline
                                            }
                                            MeoText { text: modelData.label; typeRole: "label"; elide: Text.ElideRight; Layout.fillWidth: true }
                                            MeoText { visible: modelData.value !== undefined && modelData.value !== null; text: String(modelData.value); typeRole: "label"; color: MeoTheme.onSurfaceVariant }
                                        }
                                    }
                                    Repeater {
                                        model: sec.open ? (modelData.links || []) : []
                                        MeoText {
                                            required property var modelData
                                            width: sec.width
                                            text: modelData.title || modelData.url || ""
                                            typeRole: "label"
                                            color: MeoTheme.primary
                                            elide: Text.ElideRight
                                            MouseArea {
                                                anchors.fill: parent
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: if (/^https?:\/\//.test(modelData.url || "")) Qt.openUrlExternally(modelData.url)
                                            }
                                        }
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


                    Component {
                        id: markdownBlock
                        TextEdit {
                            readOnly: true
                            selectByMouse: true
                            wrapMode: Text.Wrap
                            textFormat: TextEdit.MarkdownText
                            text: (block.text || "").replace(/:icon\[[^\]]*\]:/g, "") + (streaming ? " ▍" : "")
                            color: MeoTheme.onSurface
                            font.pixelSize: 15
                        }
                    }
                    Component {
                        id: calloutBlock
                        Rectangle {
                            readonly property color accent: block.kind === "warning" || block.kind === "caution" || block.kind === "important" ? MeoTheme.error : block.kind === "note" || block.kind === "info" ? MeoTheme.outline : MeoTheme.primary
                            implicitHeight: calloutColumn.implicitHeight + 16
                            radius: 10
                            color: MeoTheme.surfaceContainer
                            Rectangle { width: 3; height: parent.height - 12; y: 6; radius: 2; color: parent.accent }
                            Column {
                                id: calloutColumn
                                x: 14
                                y: 8
                                width: parent.width - 24
                                spacing: 2
                                Text {
                                    visible: !!block.title
                                    text: block.title || ""
                                    font.bold: true
                                    font.pixelSize: 14
                                    color: MeoTheme.onSurface
                                }
                                TextEdit {
                                    width: parent.width
                                    readOnly: true
                                    selectByMouse: true
                                    wrapMode: Text.Wrap
                                    textFormat: TextEdit.MarkdownText
                                    text: (block.text || "").replace(/:icon\[[^\]]*\]:/g, "")
                                    color: MeoTheme.onSurface
                                    font.pixelSize: 14
                                }
                            }
                        }
                    }
                    // --- drawn blocks: formulas, function graphs and charts (the core computes the geometry) begin ---
                    Component {
                        id: mathBlock
                        Rectangle {
                            implicitHeight: mathText.implicitHeight + 20
                            radius: 10
                            color: MeoTheme.surfaceContainer
                            TextEdit {
                                id: mathText
                                x: 12
                                y: 10
                                width: parent.width - 24
                                readOnly: true
                                selectByMouse: true
                                wrapMode: Text.Wrap
                                horizontalAlignment: Text.AlignHCenter
                                textFormat: TextEdit.PlainText
                                text: block.text || block.tex || ""
                                color: MeoTheme.onSurface
                                font.pixelSize: 19
                            }
                        }
                    }
                    Component {
                        id: plotBlock
                        Rectangle {
                            id: plotCard
                            readonly property var palette: ["#7c5cff", "#e8590c", "#2f9e44", "#1c7ed6", "#d6336c", "#f08c00", "#12b886", "#868e96"]
                            implicitHeight: plotColumn.implicitHeight + 20
                            radius: 14
                            color: MeoTheme.surfaceContainer
                            border.color: MeoTheme.outlineVariant
                            Column {
                                id: plotColumn
                                x: 12
                                y: 10
                                width: parent.width - 24
                                spacing: 6
                                Text { visible: !!block.title; text: block.title || ""; font.bold: true; font.pixelSize: 14; color: MeoTheme.onSurface }
                                Canvas {
                                    id: plotCanvas
                                    width: parent.width
                                    height: Math.max(180, Math.min(320, width * 0.62))
                                    onWidthChanged: requestPaint()
                                    Connections { target: MeoTheme; function onIsDarkModeChanged() { plotCanvas.requestPaint() } }
                                    onPaint: {
                                        const ctx = getContext("2d")
                                        ctx.reset()
                                        const x = block.x || [-10, 10], y = block.y || [-10, 10]
                                        const left = 40, right = 10, top = 8, bottom = 22
                                        const w = width - left - right, h = height - top - bottom
                                        if (w <= 0 || h <= 0) return
                                        const sx = v => left + (v - x[0]) / (x[1] - x[0]) * w
                                        const sy = v => top + h - (v - y[0]) / (y[1] - y[0]) * h
                                        ctx.font = "11px sans-serif"
                                        ctx.lineWidth = 1
                                        ctx.strokeStyle = MeoTheme.outlineVariant
                                        ctx.fillStyle = MeoTheme.onSurfaceVariant
                                        ctx.textAlign = "center"
                                        for (const t of (block.xticks || [])) {
                                            ctx.beginPath(); ctx.moveTo(sx(t), top); ctx.lineTo(sx(t), top + h); ctx.stroke()
                                            ctx.fillText(String(t), sx(t), top + h + 15)
                                        }
                                        ctx.textAlign = "right"
                                        for (const t of (block.yticks || [])) {
                                            ctx.beginPath(); ctx.moveTo(left, sy(t)); ctx.lineTo(left + w, sy(t)); ctx.stroke()
                                            ctx.fillText(String(t), left - 5, sy(t) + 4)
                                        }
                                        ctx.strokeStyle = MeoTheme.onSurfaceVariant
                                        ctx.lineWidth = 1.4
                                        if (x[0] <= 0 && x[1] >= 0) { ctx.beginPath(); ctx.moveTo(sx(0), top); ctx.lineTo(sx(0), top + h); ctx.stroke() }
                                        if (y[0] <= 0 && y[1] >= 0) { ctx.beginPath(); ctx.moveTo(left, sy(0)); ctx.lineTo(left + w, sy(0)); ctx.stroke() }
                                        ctx.save()
                                        ctx.beginPath(); ctx.rect(left, top, w, h); ctx.clip()
                                        ctx.lineWidth = 2
                                        ctx.lineJoin = "round"
                                        const curves = block.curves || []
                                        for (let i = 0; i < curves.length; i++) {
                                            const c = curves[i], color = plotCard.palette[i % plotCard.palette.length]
                                            ctx.strokeStyle = color
                                            ctx.fillStyle = color
                                            if (c.kind === "line") {
                                                for (const line of (c.lines || [])) {
                                                    ctx.beginPath()
                                                    for (let k = 0; k < line.length; k++) {
                                                        if (k === 0) ctx.moveTo(sx(line[k][0]), sy(line[k][1])); else ctx.lineTo(sx(line[k][0]), sy(line[k][1]))
                                                    }
                                                    ctx.stroke()
                                                }
                                            } else if (c.kind === "vline") {
                                                ctx.beginPath(); ctx.moveTo(sx(c.x), top); ctx.lineTo(sx(c.x), top + h); ctx.stroke()
                                            } else if (c.kind === "points") {
                                                for (const p of (c.points || [])) { ctx.beginPath(); ctx.arc(sx(p[0]), sy(p[1]), 4, 0, 2 * Math.PI); ctx.fill() }
                                            }
                                        }
                                        ctx.restore()
                                    }
                                }
                                Flow {
                                    width: parent.width
                                    spacing: 12
                                    Repeater {
                                        model: block.curves || []
                                        Row {
                                            required property var modelData
                                            required property int index
                                            spacing: 5
                                            Rectangle { y: 3; width: 10; height: 10; radius: 3; color: plotCard.palette[index % plotCard.palette.length] }
                                            Text { text: modelData.label || ""; font.pixelSize: 12; color: MeoTheme.onSurfaceVariant }
                                        }
                                    }
                                }
                                Text {
                                    visible: (block.errors || []).length > 0
                                    width: parent.width
                                    wrapMode: Text.Wrap
                                    text: (block.errors || []).join("\n")
                                    font.pixelSize: 12
                                    color: MeoTheme.error
                                }
                            }
                        }
                    }
                    Component {
                        id: chartBlock
                        Rectangle {
                            id: chartCard
                            readonly property var palette: ["#7c5cff", "#e8590c", "#2f9e44", "#1c7ed6", "#d6336c", "#f08c00", "#12b886", "#868e96"]
                            readonly property bool pie: block.kind === "pie"
                            implicitHeight: chartColumn.implicitHeight + 20
                            radius: 14
                            color: MeoTheme.surfaceContainer
                            border.color: MeoTheme.outlineVariant
                            Column {
                                id: chartColumn
                                x: 12
                                y: 10
                                width: parent.width - 24
                                spacing: 6
                                Text { visible: !!block.title; text: block.title || ""; font.bold: true; font.pixelSize: 14; color: MeoTheme.onSurface }
                                Canvas {
                                    id: chartCanvas
                                    width: parent.width
                                    height: chartCard.pie ? Math.max(200, Math.min(280, width * 0.6)) : Math.max(180, Math.min(300, width * 0.58))
                                    onWidthChanged: requestPaint()
                                    Connections { target: MeoTheme; function onIsDarkModeChanged() { chartCanvas.requestPaint() } }
                                    onPaint: {
                                        const ctx = getContext("2d")
                                        ctx.reset()
                                        const labels = block.labels || [], series = block.series || []
                                        const n = labels.length
                                        if (n === 0 || series.length === 0) return
                                        if (chartCard.pie) {
                                            const data = series[0].data || []
                                            let total = 0
                                            for (const v of data) total += v
                                            const cx = width / 2, cy = height / 2, r = Math.min(width, height) / 2 - 8
                                            let angle = -Math.PI / 2
                                            for (let i = 0; i < data.length; i++) {
                                                const next = angle + data[i] / total * 2 * Math.PI
                                                ctx.fillStyle = chartCard.palette[i % chartCard.palette.length]
                                                ctx.beginPath(); ctx.moveTo(cx, cy); ctx.arc(cx, cy, r, angle, next); ctx.closePath(); ctx.fill()
                                                angle = next
                                            }
                                            return
                                        }
                                        const left = 40, right = 10, top = 8, bottom = 22
                                        const w = width - left - right, h = height - top - bottom
                                        if (w <= 0 || h <= 0) return
                                        const lo = block.min, hi = block.max
                                        const sy = v => top + h - (v - lo) / (hi - lo) * h
                                        const band = w / n
                                        ctx.font = "11px sans-serif"
                                        ctx.lineWidth = 1
                                        ctx.strokeStyle = MeoTheme.outlineVariant
                                        ctx.fillStyle = MeoTheme.onSurfaceVariant
                                        ctx.textAlign = "right"
                                        for (const t of (block.ticks || [])) {
                                            ctx.beginPath(); ctx.moveTo(left, sy(t)); ctx.lineTo(left + w, sy(t)); ctx.stroke()
                                            ctx.fillText(String(t), left - 5, sy(t) + 4)
                                        }
                                        ctx.textAlign = "center"
                                        for (let i = 0; i < n; i++) {
                                            const text = String(labels[i])
                                            ctx.fillText(text.length > 10 ? text.slice(0, 9) + "…" : text, left + band * (i + 0.5), top + h + 15)
                                        }
                                        for (let s = 0; s < series.length; s++) {
                                            const color = chartCard.palette[s % chartCard.palette.length]
                                            const data = series[s].data || []
                                            if (block.kind === "bar") {
                                                const bw = band * 0.8 / series.length
                                                ctx.fillStyle = color
                                                for (let i = 0; i < data.length; i++) {
                                                    const y0 = sy(0), y1 = sy(data[i])
                                                    ctx.fillRect(left + band * i + band * 0.1 + bw * s, Math.min(y0, y1), bw, Math.abs(y1 - y0))
                                                }
                                            } else {
                                                ctx.strokeStyle = color
                                                ctx.fillStyle = color
                                                ctx.lineWidth = 2
                                                ctx.beginPath()
                                                for (let i = 0; i < data.length; i++) {
                                                    const px = left + band * (i + 0.5)
                                                    if (i === 0) ctx.moveTo(px, sy(data[i])); else ctx.lineTo(px, sy(data[i]))
                                                }
                                                ctx.stroke()
                                                for (let i = 0; i < data.length; i++) { ctx.beginPath(); ctx.arc(left + band * (i + 0.5), sy(data[i]), 3.5, 0, 2 * Math.PI); ctx.fill() }
                                            }
                                        }
                                    }
                                }
                                Flow {
                                    width: parent.width
                                    spacing: 12
                                    Repeater {
                                        model: chartCard.pie ? (block.labels || []) : (block.series || [])
                                        Row {
                                            required property var modelData
                                            required property int index
                                            spacing: 5
                                            Rectangle { y: 3; width: 10; height: 10; radius: 3; color: chartCard.palette[index % chartCard.palette.length] }
                                            Text { text: typeof modelData === "string" ? modelData : (modelData.name || ""); font.pixelSize: 12; color: MeoTheme.onSurfaceVariant }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    // --- drawn blocks end ---
                    Component {
                        id: draftBlock
                        Rectangle {
                            id: draftCard
                            property int pick: 0
                            readonly property var variant: (block.variants || [])[pick] || ({})
                            implicitHeight: draftColumn.implicitHeight + 20
                            radius: 14
                            color: MeoTheme.surfaceContainer
                            border.color: MeoTheme.outlineVariant
                            Column {
                                id: draftColumn
                                x: 12
                                y: 10
                                width: parent.width - 24
                                spacing: 6
                                Text { visible: !!block.title; text: block.title || ""; font.bold: true; font.pixelSize: 14; color: MeoTheme.onSurface }
                                Row {
                                    spacing: 4
                                    visible: (block.variants || []).length > 1
                                    Repeater {
                                        model: block.variants || []
                                        MeoButton {
                                            required property var modelData
                                            required property int index
                                            text: modelData.label || String.fromCharCode(65 + index)
                                            type: draftCard.pick === index ? "tonal" : "text"
                                            size: "xs"
                                            onClicked: draftCard.pick = index
                                        }
                                    }
                                }
                                Text {
                                    visible: !!draftCard.variant.subject
                                    width: parent.width
                                    wrapMode: Text.Wrap
                                    font.pixelSize: 13
                                    color: MeoTheme.onSurfaceVariant
                                    text: qsTr("Subject: ") + (draftCard.variant.subject || "")
                                }
                                Rectangle { width: parent.width; height: 1; color: MeoTheme.outlineVariant }
                                TextEdit {
                                    width: parent.width
                                    readOnly: true
                                    selectByMouse: true
                                    wrapMode: Text.Wrap
                                    text: draftCard.variant.body || ""
                                    color: MeoTheme.onSurface
                                    font.pixelSize: 14
                                }
                                MeoButton {
                                    anchors.right: parent.right
                                    text: (window.v.strings || {}).copy || qsTr("Copy")
                                    type: "tonal"
                                    size: "xs"
                                    onClicked: {
                                        clipboardHelper.text = draftCard.variant.body || ""
                                        clipboardHelper.selectAll()
                                        clipboardHelper.copy()
                                    }
                                }
                            }
                        }
                    }

                    ListView {
                        id: messages
                        // A centered reading column; the details card, when shown, sits to its right.
                        readonly property real reserved: inspectorCard.visible ? 232 : 0
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        anchors.topMargin: 8
                        anchors.bottomMargin: 8
                        width: Math.min(760, parent.width - reserved - 32)
                        x: Math.max(16, (parent.width - reserved - width) / 2)
                        clip: true
                        spacing: 8
                        model: window.page.messages || []
                        onCountChanged: positionViewAtEnd()
                        onContentHeightChanged: if (atYEnd || window.page.composer.busy) positionViewAtEnd()
                        delegate: Item {
                            id: messageItem
                            readonly property bool streaming: !!modelData.streaming
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
                                        id: stepRow
                                        required property var modelData
                                        property bool expanded: false
                                        readonly property bool hasMore: !!modelData.detail || (modelData.items || []).length > 0
                                        x: 16
                                        width: stepsBox.width - 32
                                        Text {
                                            width: parent.width
                                            elide: Text.ElideRight
                                            color: MeoTheme.onSurfaceVariant
                                            font.pixelSize: 13
                                            text: (stepRow.hasMore ? (stepRow.expanded ? "▾ " : "▸ ") : "   ") + (modelData.status === "done" ? "✓ " : modelData.status === "error" ? "✕ " : "… ") + modelData.title
                                            MouseArea {
                                                anchors.fill: parent
                                                enabled: stepRow.hasMore
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: stepRow.expanded = !stepRow.expanded
                                            }
                                        }
                                        Text {
                                            visible: stepRow.expanded && !!modelData.detail
                                            x: 32
                                            width: parent.width - 32
                                            wrapMode: Text.Wrap
                                            color: MeoTheme.onSurfaceVariant
                                            font.pixelSize: 12
                                            text: modelData.detail || ""
                                        }
                                        Repeater {
                                            model: stepRow.expanded ? (modelData.items || []) : []
                                            Text {
                                                required property var modelData
                                                x: 32
                                                width: parent.width - 32
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
                                MeoIconButton {
                                    type: "standard"
                                    size: "xs"
                                    icon.name: "content_copy"
                                    ToolTip.visible: hovered
                                    ToolTip.text: (window.v.strings || {}).copy || qsTr("Copy")
                                    onClicked: {
                                        clipboardHelper.text = modelData.text
                                        clipboardHelper.selectAll()
                                        clipboardHelper.copy()
                                    }
                                }
                                Repeater {
                                    model: modelData.actions || []
                                    MeoIconButton {
                                        required property var modelData
                                        type: "standard"
                                        size: "xs"
                                        // Edit / retry / regenerate: an icon each, the name in the tooltip.
                                        icon.name: modelData.action.type === "begin_edit" ? "edit" : "refresh"
                                        ToolTip.visible: hovered
                                        ToolTip.text: modelData.label
                                        onClicked: window.act(modelData.action)
                                    }
                                }
                            }
                            Rectangle {
                                id: bubble
                                y: stepsBox.height
                                anchors.right: parent.mine ? parent.right : undefined
                                width: parent.mine ? Math.min(parent.width * 0.75, blocksColumn.implicitWidth + 32) : parent.width
                                implicitHeight: blocksColumn.implicitHeight + 24
                                radius: 18
                                color: parent.mine ? MeoTheme.secondaryContainer : "transparent"
                                Column {
                                    id: blocksColumn
                                    x: 16
                                    y: 12
                                    width: bubble.width - 32
                                    spacing: 8
                                    Repeater {
                                        model: {
                                            const own = modelData.role === "user" || !modelData.blocks
                                            const list = own ? [{ type: "markdown", text: modelData.text }] : modelData.blocks
                                            return list.map((x, i) => Object.assign({ last: i === list.length - 1 }, x))
                                        }
                                        Loader {
                                            required property var modelData
                                            width: blocksColumn.width
                                            property var block: modelData
                                            property bool streaming: !!messageItem.streaming && !!modelData.last
                                            sourceComponent: block.type === "callout" ? calloutBlock : block.type === "draft" ? draftBlock : block.type === "plot" ? plotBlock : block.type === "chart" ? chartBlock : block.type === "math" ? mathBlock : markdownBlock
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // Everything under the messages. In a new chat it sits in the middle of the page
                // and glides down (fast ease-out) once the conversation starts.
                ColumnLayout {
                    id: composerBox
                    Layout.fillWidth: true
                    Layout.maximumWidth: 720
                    Layout.alignment: Qt.AlignHCenter
                    Layout.leftMargin: 12
                    Layout.rightMargin: 12
                    Layout.bottomMargin: 8
                    spacing: 4
                    readonly property var composer: window.page.composer || ({})
                    readonly property bool fresh: !!window.page.empty
                    readonly property real lift: Math.max(0, chatColumn.height - height / 2 - 8 - chatColumn.height * 0.5)
                    transform: Translate {
                        y: composerBox.fresh ? -composerBox.lift : 0
                        Behavior on y { NumberAnimation { duration: MeoTheme.reduceMotion ? 0 : 240; easing.type: Easing.OutQuart } }
                    }

                    MeoBanner {
                        visible: !!window.page.consent
                        Layout.fillWidth: true
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
                        Layout.fillWidth: true
                        readonly property var matches: /^\/\S*$/.test(input.text)
                            ? (window.page.composer.commands || []).filter(c => c.name.indexOf(input.text.toLowerCase()) === 0) : []
                        visible: matches.length > 0
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

                    // A thin pill that grows with the text, up to half the window.
                    Rectangle {
                        id: inputPill
                        Layout.fillWidth: true
                        implicitHeight: Math.min(Math.max(window.height / 2, 120), Math.max(40, inputScroll.textHeight + 14))
                        radius: Math.min(height / 2, 20)
                        color: MeoTheme.surfaceContainerHigh
                        border.width: 1
                        border.color: input.activeFocus ? MeoTheme.primary : MeoTheme.outlineVariant
                        Behavior on implicitHeight { NumberAnimation { duration: MeoTheme.reduceMotion ? 0 : 120; easing.type: Easing.OutCubic } }
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 4
                            anchors.rightMargin: 5
                            spacing: 2
                            MeoIconButton {
                                visible: !!composerBox.composer.attach
                                Layout.alignment: Qt.AlignBottom
                                type: "standard"
                                size: "xs"
                                icon.name: "attach_file"
                                onClicked: attachDialog.open()
                            }
                            ScrollView {
                                id: inputScroll
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                readonly property real textHeight: input.contentHeight
                                TextArea {
                                    id: input
                                    background: null
                                    placeholderText: composerBox.composer.placeholder || ""
                                    wrapMode: TextEdit.Wrap
                                    color: MeoTheme.onSurface
                                    placeholderTextColor: MeoTheme.onSurfaceVariant
                                    font.pixelSize: 15
                                    topPadding: 7
                                    bottomPadding: 7
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
                                        if (!text.trim().length || composerBox.composer.busy)
                                            return
                                        window.act(window.withFields(composerBox.composer.sendAction, { text: text }))
                                        text = ""
                                    }
                                }
                            }
                            MeoIconButton {
                                Layout.alignment: Qt.AlignBottom
                                size: "xs"
                                icon.name: composerBox.composer.busy ? "stop" : "arrow_upward"
                                onClicked: composerBox.composer.busy ? window.act(composerBox.composer.stopAction) : input.send()
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        readonly property var items: composerBox.composer.toolbar || []
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

                    // Starter prompts of a new chat, tucked under the box.
                    Flow {
                        visible: composerBox.fresh && commandList.matches.length === 0
                        Layout.fillWidth: true
                        Layout.topMargin: 6
                        spacing: 6
                        Repeater {
                            model: window.page.empty ? (window.page.empty.suggestions || []) : []
                            MeoButton {
                                required property var modelData
                                text: modelData.label
                                type: "outlined"
                                size: "xs"
                                onClicked: window.act(modelData.action)
                            }
                        }
                    }
                }
            }
        }
    }
}

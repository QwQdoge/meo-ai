import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MeoUI 1.0

// Live-only first run: no privileged shell and no implicit installation.
Rectangle {
    id: setup
    signal startRequested(string language, string goal)
    color: MeoTheme.surface
    focus: true
    property string language: "en"
    property string selectedSsid: ""
    property string selectedSecurity: ""
    readonly property bool chinese: language === "zh_CN"
    readonly property bool online: liveRecoveryBackend.status === "Connected"

    Keys.onEscapePressed: function(event) { event.accepted = true }

    ScrollView {
        anchors.fill: parent
        anchors.margins: 20
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
            width: Math.min(parent.width, 790)
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 18

            Item { Layout.preferredHeight: 20 }
            Label {
                Layout.fillWidth: true
                text: "Meo AI"
                font.pixelSize: 36
                font.bold: true
                color: MeoTheme.primary
            }
            Label {
                Layout.fillWidth: true
                text: setup.chinese ? "AI 安装与系统修复" : "AI installation & recovery"
                font.pixelSize: 26
                font.bold: true
                wrapMode: Text.WordWrap
            }
            Label {
                Layout.fillWidth: true
                text: setup.chinese
                    ? "先设置语言和网络，再用普通 Meo AI 对话。AI 可以帮你分析、规划；磁盘写入和系统修复仍由安装器与修复服务确认执行。"
                    : "Choose a language and network, then chat normally with Meo AI. The assistant can diagnose and plan; installation and repair actions stay with their verified owner services."
                wrapMode: Text.WordWrap
                opacity: 0.78
            }
            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: MeoTheme.outlineVariant }
            Label { text: setup.chinese ? "1 · 界面语言" : "1 · Language"; font.pixelSize: 19; font.bold: true }
            ComboBox {
                id: languageChoice
                Layout.preferredWidth: Math.min(370, parent.width)
                model: [
                    { label: "English", id: "en" },
                    { label: "简体中文", id: "zh_CN" }
                ]
                textRole: "label"
                onActivated: setup.language = model[currentIndex].id
                Accessible.name: "Language / 语言"
            }
            Label { text: setup.chinese ? "2 · 网络连接" : "2 · Internet connection"; font.pixelSize: 19; font.bold: true }
            RowLayout {
                Layout.fillWidth: true
                Label {
                    Layout.fillWidth: true
                    text: (setup.online ? "● " : "○ ") +
                          (setup.online ? (setup.chinese ? "已连接" : "Connected")
                                        : (setup.chinese ? "未连接或连接有限" : "Offline or limited")) +
                          " · " + liveRecoveryBackend.status
                    wrapMode: Text.WordWrap
                }
                Button {
                    text: setup.chinese ? "扫描" : "Refresh"
                    enabled: !liveRecoveryBackend.busy
                    onClicked: liveRecoveryBackend.refreshNetworks()
                }
                Button {
                    text: setup.chinese ? "网络设置" : "Network Settings"
                    onClicked: liveRecoveryBackend.openNetworkSettings()
                }
            }
            Label {
                visible: liveRecoveryBackend.errorText.length > 0
                Layout.fillWidth: true
                color: MeoTheme.error
                wrapMode: Text.WordWrap
                text: liveRecoveryBackend.errorText
            }
            ListView {
                id: wirelessList
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(220, Math.max(60, count * 43))
                model: liveRecoveryBackend.networks
                clip: true
                spacing: 3
                delegate: Button {
                    required property var modelData
                    width: wirelessList.width
                    height: 40
                    text: (modelData.active ? "✓  " : "◯  ") + modelData.ssid +
                          "  ·  " + modelData.signal + "%  " + modelData.security
                    highlighted: setup.selectedSsid === modelData.ssid
                    onClicked: {
                        setup.selectedSsid = modelData.ssid
                        setup.selectedSecurity = modelData.security
                        wifiPassword.text = ""
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                TextField {
                    id: wifiPassword
                    Layout.fillWidth: true
                    enabled: setup.selectedSsid.length > 0 && setup.selectedSecurity !== "--"
                    placeholderText: setup.chinese ? "Wi-Fi 密码（开放网络无需输入）" : "Wi-Fi password (not needed for open networks)"
                    echoMode: TextInput.Password
                    Accessible.name: placeholderText
                }
                Button {
                    text: setup.chinese ? "连接" : "Connect"
                    enabled: setup.selectedSsid.length > 0 && !liveRecoveryBackend.busy
                    onClicked: {
                        liveRecoveryBackend.connectWifi(setup.selectedSsid, wifiPassword.text)
                        wifiPassword.text = ""
                    }
                }
            }
            Label {
                Layout.fillWidth: true
                text: setup.chinese
                    ? "没有 Wi-Fi 也能进入聊天，但云端模型可能无法连接。密码不会保存到 Meo AI 设置。"
                    : "You can proceed offline, but cloud models may be unavailable. Meo AI does not save the Wi-Fi password."
                opacity: 0.68
                wrapMode: Text.WordWrap
            }
            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: MeoTheme.outlineVariant }
            Label { text: setup.chinese ? "3 · 你想做什么？" : "3 · What would you like to do?"; font.pixelSize: 19; font.bold: true }
            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                Button {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 50
                    text: setup.chinese ? "使用 AI 安装系统" : "Install with AI"
                    onClicked: setup.startRequested(setup.language, "install")
                }
                Button {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 50
                    text: setup.chinese ? "使用 AI 修复系统" : "Repair with AI"
                    onClicked: setup.startRequested(setup.language, "repair")
                }
            }
            Label {
                Layout.fillWidth: true
                text: setup.chinese
                    ? "也可以在 Live 桌面打开普通安装器或 Quick Repair。AI 聊天不会自动获得 root 权限。"
                    : "The normal Installer and Quick Repair remain available from the Live desktop. Chat never receives automatic root access."
                wrapMode: Text.WordWrap
                opacity: 0.68
            }
            Item { Layout.preferredHeight: 20 }
        }
    }
    Component.onCompleted: liveRecoveryBackend.refreshNetworks()
}

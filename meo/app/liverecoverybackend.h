#pragma once

#include <QObject>
#include <QProcess>
#include <QString>
#include <QVariantList>

// Unprivileged, Live-only NetworkManager setup for the Meo AI recovery entry.
// Never exposes a general command runner or logs a Wi-Fi password.
class LiveRecoveryBackend final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariantList networks READ networks NOTIFY networksChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY stateChanged)
    Q_PROPERTY(QString status READ status NOTIFY stateChanged)
    Q_PROPERTY(QString errorText READ errorText NOTIFY stateChanged)
public:
    explicit LiveRecoveryBackend(bool active, QObject *parent = nullptr);
    QVariantList networks() const { return m_networks; }
    bool busy() const { return m_scan != nullptr || m_connect != nullptr; }
    QString status() const { return m_status; }
    QString errorText() const { return m_error; }

    Q_INVOKABLE void refreshNetworks();
    Q_INVOKABLE void connectWifi(const QString &ssid, const QString &password);
    Q_INVOKABLE void openNetworkSettings();
    Q_INVOKABLE void openInstaller();
    Q_INVOKABLE void openQuickRepair();
signals:
    void networksChanged();
    void stateChanged();
private:
    void updateStatus();
    bool m_active = false;
    QVariantList m_networks;
    QProcess *m_scan = nullptr;
    QProcess *m_connect = nullptr;
    QString m_status = QStringLiteral("Checking network…");
    QString m_error;
    QString m_pendingPassword;
    bool m_passwordSupplied = false;
};

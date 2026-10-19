#include "liverecoverybackend.h"

#include <QProcessEnvironment>
#include <QSet>

namespace {
// nmcli's --escape yes escapes delimiter colons and backslashes. Do not parse
// SSIDs by an ordinary split(':') because SSIDs may contain colons.
QStringList fields(const QString &line) {
    QStringList result;
    QString item;
    bool escaped = false;
    for (const QChar character : line) {
        if (escaped) { item.append(character); escaped = false; }
        else if (character == QLatin1Char('\\')) escaped = true;
        else if (character == QLatin1Char(':')) { result.append(item); item.clear(); }
        else item.append(character);
    }
    if (escaped) item.append(QLatin1Char('\\'));
    result.append(item);
    return result;
}
void englishNmcli(QProcess *process) {
    QProcessEnvironment environment = QProcessEnvironment::systemEnvironment();
    environment.insert(QStringLiteral("LC_ALL"), QStringLiteral("C"));
    process->setProcessEnvironment(environment);
}
}

LiveRecoveryBackend::LiveRecoveryBackend(QObject *parent) : QObject(parent) {
    updateStatus();
}

void LiveRecoveryBackend::updateStatus() {
    QProcess process;
    englishNmcli(&process);
    process.start(QStringLiteral("/usr/bin/nmcli"),
                  {QStringLiteral("-t"), QStringLiteral("-f"), QStringLiteral("STATE"),
                   QStringLiteral("general")});
    if (!process.waitForStarted(1000) || !process.waitForFinished(2000)) {
        process.kill();
        m_status = QStringLiteral("NetworkManager is unavailable");
    } else {
        const QString state = QString::fromUtf8(process.readAllStandardOutput()).trimmed();
        m_status = state.startsWith(QStringLiteral("connected"))
                       ? QStringLiteral("Connected") : QStringLiteral("Offline");
    }
    emit stateChanged();
}

void LiveRecoveryBackend::refreshNetworks() {
    if (busy()) return;
    m_error.clear();
    m_scan = new QProcess(this);
    englishNmcli(m_scan);
    connect(m_scan, &QProcess::finished, this, [this](int code, QProcess::ExitStatus exitStatus) {
        const QString output = QString::fromUtf8(m_scan->readAllStandardOutput());
        const QString error = QString::fromUtf8(m_scan->readAllStandardError()).trimmed();
        m_scan->deleteLater();
        m_scan = nullptr;
        if (code != 0 || exitStatus != QProcess::NormalExit) {
            m_error = error.left(400);
        } else {
            QVariantList networks;
            QSet<QString> seen;
            for (const QString &line : output.split(QLatin1Char('\n'), Qt::SkipEmptyParts)) {
                const QStringList values = fields(line);
                if (values.size() != 4 || values.at(1).isEmpty() || seen.contains(values.at(1)))
                    continue;
                seen.insert(values.at(1));
                networks.append(QVariantMap{
                    {QStringLiteral("ssid"), values.at(1)},
                    {QStringLiteral("signal"), values.at(2).toInt()},
                    {QStringLiteral("security"), values.at(3)},
                    {QStringLiteral("active"), values.at(0) == QStringLiteral("*")}
                });
            }
            m_networks = networks;
            emit networksChanged();
        }
        updateStatus();
    });
    m_scan->start(QStringLiteral("/usr/bin/nmcli"),
                  {QStringLiteral("-t"), QStringLiteral("-e"), QStringLiteral("yes"),
                   QStringLiteral("-f"), QStringLiteral("IN-USE,SSID,SIGNAL,SECURITY"),
                   QStringLiteral("device"), QStringLiteral("wifi"), QStringLiteral("list"),
                   QStringLiteral("--rescan"), QStringLiteral("yes")});
    emit stateChanged();
}

void LiveRecoveryBackend::connectWifi(const QString &ssid, const QString &password) {
    if (busy() || ssid.isEmpty() || ssid.size() > 128 || ssid.contains(QChar::Null)) return;
    m_error.clear();
    m_status = QStringLiteral("Connecting…");
    m_pendingPassword = password;
    m_passwordSupplied = false;
    m_connect = new QProcess(this);
    englishNmcli(m_connect);
    // --ask receives credentials over stdin. The secret is never a command-line
    // argument, shell fragment, persisted QSettings value or diagnostic log.
    connect(m_connect, &QProcess::readyReadStandardOutput, this, [this] {
        if (!m_connect) return;
        const QString prompt = QString::fromUtf8(m_connect->readAllStandardOutput());
        if (!m_passwordSupplied && prompt.contains(QStringLiteral("Password"), Qt::CaseInsensitive)) {
            m_connect->write(m_pendingPassword.toUtf8() + '\n');
            m_pendingPassword.fill(QChar::Null);
            m_pendingPassword.clear();
            m_passwordSupplied = true;
        }
    });
    connect(m_connect, &QProcess::finished, this, [this](int code, QProcess::ExitStatus status) {
        // Do not display arbitrary nmcli stderr: it can echo sensitive input.
        m_pendingPassword.fill(QChar::Null);
        m_pendingPassword.clear();
        m_connect->deleteLater();
        m_connect = nullptr;
        if (code != 0 || status != QProcess::NormalExit)
            m_error = QStringLiteral("Connection failed. Check the password or use Network Settings.");
        updateStatus();
    });
    m_connect->start(QStringLiteral("/usr/bin/nmcli"),
                     {QStringLiteral("--ask"), QStringLiteral("--wait"), QStringLiteral("25"),
                      QStringLiteral("device"), QStringLiteral("wifi"),
                      QStringLiteral("connect"), ssid});
    emit stateChanged();
}

void LiveRecoveryBackend::openNetworkSettings() {
    QProcess::startDetached(QStringLiteral("/usr/bin/systemsettings"),
                            {QStringLiteral("kcm_networkmanagement")});
}

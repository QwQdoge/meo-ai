#include "usagebackend.h"

#include <QJsonDocument>
#include <QJsonObject>
#include <QProcessEnvironment>
#include <QStringList>

UsageBackend::UsageBackend(QObject *parent)
    : QObject(parent)
{
    connect(&m_process, &QProcess::finished, this, &UsageBackend::finish);
    refresh();
}

void UsageBackend::refresh()
{
    run(QStringLiteral("dashboard"));
}

void UsageBackend::importHistory()
{
    run(QStringLiteral("refresh"));
}

void UsageBackend::syncNow()
{
    run(QStringLiteral("sync"));
}

void UsageBackend::run(const QString &command)
{
    if (m_process.state() != QProcess::NotRunning)
        return;

    const QString override = qEnvironmentVariable("MEO_AI_USAGE_PYTHON").trimmed();
    const QString python = override.isEmpty() ? QStringLiteral("python3") : override;
    setBusy(true);
    if (command == QLatin1String("refresh"))
        setStatus(tr("Importing Codex and Claude Code history…"));
    else if (command == QLatin1String("sync"))
        setStatus(tr("Syncing AI activity…"));
    else
        setStatus(tr("Loading AI activity…"));

    m_process.setProcessChannelMode(QProcess::SeparateChannels);
    m_process.start(python, {QStringLiteral("-m"), QStringLiteral("meo.usage.cli"), command});
}

void UsageBackend::finish(int exitCode, QProcess::ExitStatus exitStatus)
{
    setBusy(false);
    const QByteArray output = m_process.readAllStandardOutput();
    const QByteArray errorOutput = m_process.readAllStandardError();
    if (exitStatus != QProcess::NormalExit || exitCode != 0) {
        const QJsonDocument errorDocument = QJsonDocument::fromJson(errorOutput);
        const QString message = errorDocument.isObject()
            ? errorDocument.object().value(QStringLiteral("error")).toString()
            : QString::fromUtf8(errorOutput).trimmed();
        setStatus(message.isEmpty() ? tr("AI activity could not be loaded.") : message);
        return;
    }

    const QJsonDocument document = QJsonDocument::fromJson(output);
    if (!document.isObject()) {
        setStatus(tr("AI activity returned invalid data."));
        return;
    }
    const QJsonObject object = document.object();
    if (object.contains(QStringLiteral("error"))) {
        setStatus(object.value(QStringLiteral("error")).toString());
        return;
    }

    m_dashboard = object.toVariantMap();
    emit dashboardChanged();
    const bool cloud = object.value(QStringLiteral("data_source")).toString() == QLatin1String("cloud");
    const bool configured = object.value(QStringLiteral("sync_configured")).toBool();
    if (cloud)
        setStatus(tr("Synced with Meo Account"));
    else if (configured)
        setStatus(tr("Showing local activity · cloud sync is available"));
    else
        setStatus(tr("Showing local activity · sign in to sync"));
}

void UsageBackend::setBusy(bool value)
{
    if (m_busy == value)
        return;
    m_busy = value;
    emit busyChanged();
}

void UsageBackend::setStatus(const QString &value)
{
    if (m_status == value)
        return;
    m_status = value;
    emit statusChanged();
}

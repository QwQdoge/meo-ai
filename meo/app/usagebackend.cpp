#include "usagebackend.h"

#include <QDBusConnection>
#include <QDBusInterface>
#include <QDBusReply>
#include <QJsonDocument>
#include <QJsonObject>
#include <QStandardPaths>

namespace
{
const QString kAccountService = QStringLiteral("org.meo.Accounts1");
const QString kUsagePath = QStringLiteral("/org/meo/Accounts1/Usage");
const QString kUsageInterface = QStringLiteral("org.meo.Accounts1.Usage");
const QString kClientId = QStringLiteral("org.meo.MeoAI");
constexpr int kSyncBatchSize = 250;

QString processError(const QByteArray &errorOutput)
{
    const QJsonDocument errorDocument = QJsonDocument::fromJson(errorOutput);
    if (errorDocument.isObject())
        return errorDocument.object().value(QStringLiteral("error")).toString().trimmed();
    return QString::fromUtf8(errorOutput).trimmed();
}
}

UsageBackend::UsageBackend(QObject *parent)
    : QObject(parent)
{
    connect(&m_process, &QProcess::finished, this, &UsageBackend::finish);
    m_brokerPoll.setInterval(180);
    connect(&m_brokerPoll, &QTimer::timeout, this, &UsageBackend::pollBrokerRequest);
    QTimer::singleShot(0, this, &UsageBackend::refresh);
}

void UsageBackend::refresh()
{
    if (m_busy)
        return;
    setBusy(true);
    setStatus(tr("Loading AI activity…"));
    run(QStringLiteral("dashboard"), {QStringLiteral("--local-only")}, QStringLiteral("refresh"));
}

void UsageBackend::importHistory()
{
    if (m_busy)
        return;
    startImportAndSync();
}

void UsageBackend::syncNow()
{
    if (m_busy)
        return;
    startImportAndSync();
}

void UsageBackend::startImportAndSync()
{
    setBusy(true);
    m_uploadedEvents = 0;
    m_pendingEvents = {};
    m_nextEventIndex = 0;
    m_currentBatchSize = 0;
    setStatus(tr("Importing Codex and Claude Code history…"));
    run(QStringLiteral("import"), {QStringLiteral("--local-only")}, QStringLiteral("import"));
}

void UsageBackend::run(const QString &command, const QStringList &arguments,
                       const QString &purpose)
{
    if (m_process.state() != QProcess::NotRunning)
        return;

    m_processPurpose = purpose;
    m_process.setProcessChannelMode(QProcess::SeparateChannels);

    const QString commandOverride = qEnvironmentVariable("MEO_AI_USAGE_COMMAND").trimmed();
    const QString installedCommand = commandOverride.isEmpty()
        ? QStandardPaths::findExecutable(QStringLiteral("meo-ai-usage"))
        : commandOverride;
    if (!installedCommand.isEmpty()) {
        QStringList processArguments{command};
        processArguments.append(arguments);
        m_process.start(installedCommand, processArguments);
        return;
    }

    // Source checkouts do not have the packaged wrapper yet. Keeping this
    // fallback makes local development and CI previews work without install.
    const QString pythonOverride = qEnvironmentVariable("MEO_AI_USAGE_PYTHON").trimmed();
    const QString python = pythonOverride.isEmpty() ? QStringLiteral("python3") : pythonOverride;
    QStringList processArguments{QStringLiteral("-m"), QStringLiteral("meo.usage.cli"), command};
    processArguments.append(arguments);
    m_process.start(python, processArguments);
}

void UsageBackend::finish(int exitCode, QProcess::ExitStatus exitStatus)
{
    const QString purpose = m_processPurpose;
    m_processPurpose.clear();
    const QByteArray output = m_process.readAllStandardOutput();
    const QByteArray errorOutput = m_process.readAllStandardError();
    if (exitStatus != QProcess::NormalExit || exitCode != 0) {
        const QString message = processError(errorOutput);
        finishLocal(message.isEmpty() ? tr("AI activity could not be loaded.") : message);
        return;
    }

    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(output, &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        finishLocal(tr("AI activity returned invalid data."));
        return;
    }
    const QJsonObject object = document.object();
    if (object.contains(QStringLiteral("error"))) {
        finishLocal(object.value(QStringLiteral("error")).toString());
        return;
    }

    if (purpose == QLatin1String("export")) {
        m_pendingEvents = object.value(QStringLiteral("events")).toArray();
        m_nextEventIndex = 0;
        m_currentBatchSize = 0;
        startNextSyncBatch();
        return;
    }

    QVariantMap localDashboard = object.toVariantMap();
    localDashboard.insert(QStringLiteral("data_source"), QStringLiteral("local"));
    localDashboard.insert(QStringLiteral("sync_configured"), false);
    setDashboard(localDashboard);

    if (purpose == QLatin1String("import")) {
        setStatus(tr("Preparing activity for Meo Account…"));
        run(QStringLiteral("export"), {QStringLiteral("--local-only")}, QStringLiteral("export"));
        return;
    }

    startCloudDashboard();
}

bool UsageBackend::startBrokerOperation(const QString &action, const QByteArray &payload)
{
    QDBusInterface broker(kAccountService, kUsagePath, kUsageInterface,
                          QDBusConnection::sessionBus());
    if (!broker.isValid())
        return false;

    const QDBusReply<QString> reply = broker.call(
        QStringLiteral("StartUsageOperation"), kClientId, action,
        QString::fromUtf8(payload));
    if (!reply.isValid() || reply.value().isEmpty())
        return false;

    m_brokerRequestId = reply.value();
    m_brokerAction = action;
    m_brokerPoll.start();
    QTimer::singleShot(0, this, &UsageBackend::pollBrokerRequest);
    return true;
}

void UsageBackend::startNextSyncBatch()
{
    if (m_nextEventIndex >= m_pendingEvents.size()) {
        startCloudDashboard();
        return;
    }

    QJsonArray batch;
    const int end = qMin(m_nextEventIndex + kSyncBatchSize, m_pendingEvents.size());
    for (int index = m_nextEventIndex; index < end; ++index)
        batch.append(m_pendingEvents.at(index));
    m_currentBatchSize = batch.size();
    setStatus(tr("Syncing AI activity… %1/%2")
                  .arg(m_nextEventIndex)
                  .arg(m_pendingEvents.size()));

    if (!startBrokerOperation(QStringLiteral("sync"),
                              QJsonDocument(batch).toJson(QJsonDocument::Compact))) {
        finishLocal(tr("Showing local activity · Meo Account sync is unavailable"));
    }
}

void UsageBackend::startCloudDashboard()
{
    setStatus(m_uploadedEvents > 0
                  ? tr("Activity uploaded · loading synced summary…")
                  : tr("Loading synced activity…"));
    const QByteArray payload = QJsonDocument(
        QJsonObject{{QStringLiteral("days"), 365}}).toJson(QJsonDocument::Compact);
    if (!startBrokerOperation(QStringLiteral("dashboard"), payload))
        finishLocal(tr("Showing local activity · Meo Account sync is unavailable"));
}

void UsageBackend::pollBrokerRequest()
{
    if (m_brokerRequestId.isEmpty()) {
        m_brokerPoll.stop();
        return;
    }

    QDBusInterface broker(kAccountService, kUsagePath, kUsageInterface,
                          QDBusConnection::sessionBus());
    const QDBusReply<QString> reply = broker.call(
        QStringLiteral("GetUsageRequest"), kClientId, m_brokerRequestId);
    if (!reply.isValid() || reply.value().isEmpty()) {
        m_brokerPoll.stop();
        m_brokerRequestId.clear();
        m_brokerAction.clear();
        finishLocal(tr("Showing local activity · Meo Account sync was interrupted"));
        return;
    }

    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(reply.value().toUtf8(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        m_brokerPoll.stop();
        m_brokerRequestId.clear();
        m_brokerAction.clear();
        finishLocal(tr("Showing local activity · Meo Account returned invalid sync state"));
        return;
    }

    const QJsonObject request = document.object();
    const QString state = request.value(QStringLiteral("state")).toString();
    if (state == QLatin1String("pending"))
        return;

    m_brokerPoll.stop();
    const QString completedAction = m_brokerAction;
    m_brokerRequestId.clear();
    m_brokerAction.clear();

    if (state != QLatin1String("completed")) {
        const QString error = request.value(QStringLiteral("error")).toString().trimmed();
        if (m_uploadedEvents > 0)
            finishLocal(error.isEmpty()
                            ? tr("Activity uploaded, but the synced summary is unavailable")
                            : tr("Activity uploaded · %1").arg(error));
        else
            finishLocal(error.isEmpty()
                            ? tr("Showing local activity · sign in to Meo Account to sync")
                            : error);
        return;
    }

    const QJsonObject result = request.value(QStringLiteral("result")).toObject();
    if (completedAction == QLatin1String("sync")) {
        const int uploaded = result.value(QStringLiteral("uploaded")).toInt(m_currentBatchSize);
        m_uploadedEvents += qMax(0, uploaded);
        m_nextEventIndex += m_currentBatchSize;
        m_currentBatchSize = 0;
        startNextSyncBatch();
        return;
    }

    QVariantMap cloudDashboard = result.toVariantMap();
    cloudDashboard.insert(QStringLiteral("data_source"), QStringLiteral("cloud"));
    cloudDashboard.insert(QStringLiteral("sync_configured"), true);
    if (m_uploadedEvents > 0) {
        cloudDashboard.insert(QStringLiteral("sync"), QVariantMap{
            {QStringLiteral("configured"), true},
            {QStringLiteral("uploaded"), m_uploadedEvents},
        });
    }
    setDashboard(cloudDashboard);
    setBusy(false);
    setStatus(m_uploadedEvents > 0
                  ? tr("Synced %1 activity events with Meo Account").arg(m_uploadedEvents)
                  : tr("Synced with Meo Account"));
    m_pendingEvents = {};
    m_nextEventIndex = 0;
    m_uploadedEvents = 0;
}

void UsageBackend::finishLocal(const QString &status)
{
    m_brokerPoll.stop();
    m_brokerRequestId.clear();
    m_brokerAction.clear();
    m_pendingEvents = {};
    m_nextEventIndex = 0;
    m_currentBatchSize = 0;
    m_uploadedEvents = 0;
    setBusy(false);
    setStatus(status);
}

void UsageBackend::setDashboard(const QVariantMap &dashboard)
{
    if (m_dashboard == dashboard)
        return;
    m_dashboard = dashboard;
    emit dashboardChanged();
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

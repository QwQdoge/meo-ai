#pragma once

#include <QJsonArray>
#include <QObject>
#include <QProcess>
#include <QStringList>
#include <QTimer>
#include <QVariantMap>

class UsageBackend final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QVariantMap dashboard READ dashboard NOTIFY dashboardChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)

public:
    explicit UsageBackend(QObject *parent = nullptr);

    QVariantMap dashboard() const { return m_dashboard; }
    bool busy() const { return m_busy; }
    QString status() const { return m_status; }

    Q_INVOKABLE void refresh();
    Q_INVOKABLE void importHistory();
    Q_INVOKABLE void syncNow();

signals:
    void dashboardChanged();
    void busyChanged();
    void statusChanged();

private:
    void run(const QString &command, const QStringList &arguments, const QString &purpose);
    void finish(int exitCode, QProcess::ExitStatus exitStatus);
    void startImportAndSync();
    void startCloudDashboard();
    void startNextSyncBatch();
    bool startBrokerOperation(const QString &action, const QByteArray &payload);
    void pollBrokerRequest();
    void finishLocal(const QString &status);
    void setDashboard(const QVariantMap &dashboard);
    void setBusy(bool value);
    void setStatus(const QString &value);

    QProcess m_process;
    QTimer m_brokerPoll;
    QVariantMap m_dashboard;
    QJsonArray m_pendingEvents;
    QString m_processPurpose;
    QString m_brokerRequestId;
    QString m_brokerAction;
    int m_nextEventIndex = 0;
    int m_currentBatchSize = 0;
    int m_uploadedEvents = 0;
    bool m_busy = false;
    QString m_status;
};

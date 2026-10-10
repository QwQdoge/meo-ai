#pragma once

#include <QObject>
#include <QProcess>
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
    void run(const QString &command);
    void finish(int exitCode, QProcess::ExitStatus exitStatus);
    void setBusy(bool value);
    void setStatus(const QString &value);

    QProcess m_process;
    QVariantMap m_dashboard;
    bool m_busy = false;
    QString m_status;
};

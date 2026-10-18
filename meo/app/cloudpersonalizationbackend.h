#pragma once

#include <QObject>
#include <QString>
#include <QVariantList>
#include <QVariantMap>

// Qt/QML only sees account-scoped settings and memory data. The bearer token
// never leaves Meo Account's exact-executable-checked D-Bus broker.
class CloudPersonalizationBackend final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool signedIn READ signedIn NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(QString status READ status NOTIFY changed)
    Q_PROPERTY(QVariantMap settings READ settings NOTIFY changed)
    Q_PROPERTY(QVariantList memories READ memories NOTIFY changed)
    Q_PROPERTY(bool archived READ archived NOTIFY changed)
public:
    explicit CloudPersonalizationBackend(QObject *parent = nullptr);

    bool signedIn() const { return m_signedIn; }
    bool busy() const { return m_busy; }
    QString status() const { return m_status; }
    QVariantMap settings() const { return m_settings; }
    QVariantList memories() const { return m_memories; }
    bool archived() const { return m_archived; }

    Q_INVOKABLE void refresh(bool archived = false);
    Q_INVOKABLE void saveSettings(const QString &instructions, bool enabled);
    Q_INVOKABLE void addMemory(const QString &content);
    Q_INVOKABLE void updateMemory(const QString &id, int version, const QString &content);
    Q_INVOKABLE void setMemoryEnabled(const QString &id, int version, bool enabled);
    Q_INVOKABLE void archiveMemory(const QString &id, int version, bool archived);
    Q_INVOKABLE void deleteMemory(const QString &id);

signals:
    void changed();
    void memoryCreated();

private slots:
    void accountChanged();
    void requestChanged(const QString &requestId, const QString &state,
                        const QVariantMap &result);

private:
    bool start(const QString &action, const QVariantMap &arguments);
    void inspect(const QString &requestId);
    void fail(const QString &message);

    bool m_signedIn = false;
    bool m_busy = false;
    bool m_archived = false;
    QString m_status;
    QString m_activeId;
    QString m_activeAction;
    QVariantMap m_settings;
    QVariantList m_memories;
};

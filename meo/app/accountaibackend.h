#pragma once

#include <QObject>
#include <QString>
#include <QVariantList>
#include <QVariantMap>

class AccountAiBackend final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool serviceAvailable READ serviceAvailable NOTIFY changed)
    Q_PROPERTY(bool signedIn READ signedIn NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(QString status READ status NOTIFY changed)
    Q_PROPERTY(QString accountName READ accountName NOTIFY changed)
    Q_PROPERTY(QString accountEmail READ accountEmail NOTIFY changed)
    Q_PROPERTY(QString avatarUrl READ avatarUrl NOTIFY changed)
    Q_PROPERTY(QVariantList connections READ connections NOTIFY changed)
    Q_PROPERTY(QVariantList models READ models NOTIFY changed)
    Q_PROPERTY(QString selectedConnectionId READ selectedConnectionId NOTIFY changed)
    Q_PROPERTY(QString selectedModelId READ selectedModelId NOTIFY changed)

public:
    explicit AccountAiBackend(QObject *parent = nullptr);

    bool serviceAvailable() const { return m_serviceAvailable; }
    bool signedIn() const { return m_signedIn; }
    bool busy() const { return m_busy; }
    QString status() const { return m_status; }
    QString accountName() const { return m_accountName; }
    QString accountEmail() const { return m_accountEmail; }
    QString avatarUrl() const { return m_avatarUrl; }
    QVariantList connections() const { return m_connections; }
    QVariantList models() const { return m_models; }
    QString selectedConnectionId() const { return m_selectedConnectionId; }
    QString selectedModelId() const { return m_selectedModelId; }

    Q_INVOKABLE void refresh();
    Q_INVOKABLE bool signIn();
    Q_INVOKABLE bool openAccountPage(const QString &page);
    Q_INVOKABLE void discoverModels(const QString &connectionId);
    Q_INVOKABLE bool selectConnection(const QString &connectionId);
    Q_INVOKABLE bool selectModel(const QString &modelId);
    Q_INVOKABLE bool openProviderSettings();

signals:
    void changed();
    void modelActivationRequested(const QString &connectionId, const QString &modelId);

private slots:
    void handleAccountChanged();
    void handleRequestChanged(const QString &requestId, const QString &state,
                              const QVariantMap &result);

private:
    enum class RequestKind {
        None,
        Authentication,
        ModelDiscovery,
    };

    QVariantMap connectionById(const QString &connectionId) const;
    bool modelExists(const QString &modelId) const;
    void loadPreferences();
    void savePreferences() const;
    void setStatus(const QString &status);
    void setBusy(bool busy);
    void clearAccountIdentity();

    bool m_serviceAvailable = false;
    bool m_signedIn = false;
    bool m_busy = false;
    QString m_status;
    QString m_accountName;
    QString m_accountEmail;
    QString m_avatarUrl;
    QVariantList m_connections;
    QVariantList m_models;
    QString m_selectedConnectionId;
    QString m_selectedModelId;
    QString m_activeRequestId;
    QString m_discoveryConnectionId;
    RequestKind m_activeRequestKind = RequestKind::None;
};

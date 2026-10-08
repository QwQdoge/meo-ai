#pragma once
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QObject>
#include <QUrl>
#include <QVariantList>
#include <functional>

class AgentClient : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(bool actionBusy READ actionBusy NOTIFY changed)
    Q_PROPERTY(bool serviceMode READ serviceMode CONSTANT)
    Q_PROPERTY(QString status READ status NOTIFY changed)
    Q_PROPERTY(QVariantList options READ options NOTIFY changed)
public:
    explicit AgentClient(QObject *parent = nullptr);
    bool busy() const { return m_reply != nullptr; }
    bool actionBusy() const { return m_actionReply != nullptr; }
    bool serviceMode() const { return m_serviceMode; }
    QString status() const { return m_status; }
    QVariantList options() const { return m_options; }
    Q_INVOKABLE void send(const QString &text);
    Q_INVOKABLE void choose(int index);
    Q_INVOKABLE void cancel();
    Q_INVOKABLE void newChat();
signals:
    void changed();
    void message(const QString &role, const QString &text);
    void delta(const QString &text);
    void toolEvent(const QVariantMap &event);
    void resetChat();
private:
    void requestLegacy(const QString &text);
    void consumeLegacy();
    void ensureServiceConversation(const std::function<void()> &then);
    void loadServiceHistory();
    void sendService(const QString &text);
    void reconnectServiceStream();
    void attachServiceStream(QNetworkReply *reply);
    void consumeService();
    void submitServiceCancel();
    void postServiceAction(const QUrl &url, const QByteArray &body, const std::function<void(QNetworkReply *)> &onSuccess);
    QUrl validatedOrigin(const QByteArray &variable, const QString &fallback = QString()) const;
    QNetworkAccessManager m_network;
    QNetworkReply *m_reply = nullptr;
    QNetworkReply *m_actionReply = nullptr;
    QByteArray m_buffer;
    QString m_user;
    QString m_conversationId;
    QString m_requestId;
    QString m_decisionId;
    QString m_status;
    QVariantList m_options;
    bool m_done = false;
    bool m_serviceMode = false;
    bool m_cancelPending = false;
    int m_lastEventSeq = 0;
    int m_reconnectAttempts = 0;
};

#pragma once
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QObject>
#include <QUrl>
#include <QVariantList>
#include <QVariantMap>
#include <functional>

class AgentClient : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(bool actionBusy READ actionBusy NOTIFY changed)
    Q_PROPERTY(bool metadataBusy READ metadataBusy NOTIFY changed)
    Q_PROPERTY(bool serviceMode READ serviceMode CONSTANT)
    Q_PROPERTY(QString status READ status NOTIFY changed)
    Q_PROPERTY(QString metadataStatus READ metadataStatus NOTIFY changed)
    Q_PROPERTY(QVariantList options READ options NOTIFY changed)
    Q_PROPERTY(QVariantMap agentState READ agentState NOTIFY changed)
    Q_PROPERTY(QVariantList models READ models NOTIFY changed)
    Q_PROPERTY(QVariantList modelRoles READ modelRoles NOTIFY changed)
    Q_PROPERTY(QVariantList skills READ skills NOTIFY changed)
    Q_PROPERTY(QVariantList mcpServers READ mcpServers NOTIFY changed)
    Q_PROPERTY(QVariantList controls READ controls NOTIFY changed)
    Q_PROPERTY(QVariantMap responseMetadata READ responseMetadata NOTIFY changed)
public:
    explicit AgentClient(QObject *parent = nullptr);
    bool busy() const { return m_reply != nullptr; }
    bool actionBusy() const { return m_actionReply != nullptr; }
    bool metadataBusy() const { return m_metadataReply != nullptr; }
    bool serviceMode() const { return m_serviceMode; }
    QString status() const { return m_status; }
    QString metadataStatus() const { return m_metadataStatus; }
    QVariantList options() const { return m_options; }
    QVariantMap agentState() const { return m_agentState; }
    QVariantList models() const { return m_models; }
    QVariantList modelRoles() const { return m_modelRoles; }
    QVariantList skills() const { return m_skills; }
    QVariantList mcpServers() const { return m_mcpServers; }
    QVariantList controls() const { return m_controls; }
    QVariantMap responseMetadata() const { return m_responseMetadata; }
    Q_INVOKABLE void send(const QString &text);
    Q_INVOKABLE void choose(int index);
    Q_INVOKABLE void cancel();
    Q_INVOKABLE void newChat();
    Q_INVOKABLE void refreshServiceMetadata();
    Q_INVOKABLE void setModelRole(const QString &roleId, const QString &modelId);
    Q_INVOKABLE void setControl(const QString &controlId, const QVariant &value);
signals:
    void changed();
    void message(const QString &role, const QString &text);
    void delta(const QString &text);
    void toolEvent(const QVariantMap &event);
    void presentationEvent(const QVariantMap &event);
    void responseMetaEvent(const QVariantMap &event);
    void resetChat();
private:
    void requestLegacy(const QString &text);
    void consumeLegacy();
    void ensureServiceConversation(const std::function<void()> &then);
    void loadServiceHistory();
    void sendService(const QString &text, bool emitAssistantPlaceholder = true);
    void reconnectServiceStream();
    void attachServiceStream(QNetworkReply *reply);
    void consumeService();
    void submitServiceCancel();
    void fetchServiceMetadataStep(int step, bool hadError);
    void postServiceAction(const QUrl &url, const QByteArray &body, const std::function<void(QNetworkReply *)> &onSuccess);
    QUrl validatedOrigin(const QByteArray &variable, const QString &fallback = QString()) const;
    QNetworkAccessManager m_network;
    QNetworkReply *m_reply = nullptr;
    QNetworkReply *m_actionReply = nullptr;
    QNetworkReply *m_metadataReply = nullptr;
    QByteArray m_buffer;
    QString m_user;
    QString m_conversationId;
    QString m_requestId;
    QString m_decisionId;
    QString m_pendingServiceText;
    QString m_status;
    QString m_metadataStatus;
    QVariantList m_options;
    QVariantMap m_agentState;
    QVariantList m_models;
    QVariantList m_modelRoles;
    QVariantList m_skills;
    QVariantList m_mcpServers;
    QVariantList m_controls;
    QVariantMap m_responseMetadata;
    bool m_done = false;
    bool m_serviceMode = false;
    bool m_cancelPending = false;
    bool m_staleConversationRetryUsed = false;
    int m_lastEventSeq = 0;
    int m_reconnectAttempts = 0;
};

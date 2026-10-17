#pragma once
#include <QByteArray>
#include <QList>
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
    Q_PROPERTY(bool conversationSearchBusy READ conversationSearchBusy NOTIFY changed)
    Q_PROPERTY(bool serviceMode READ serviceMode CONSTANT)
    Q_PROPERTY(QString status READ status NOTIFY changed)
    Q_PROPERTY(QString metadataStatus READ metadataStatus NOTIFY changed)
    Q_PROPERTY(bool requestFailed READ requestFailed NOTIFY changed)
    Q_PROPERTY(bool requestRetryable READ requestRetryable NOTIFY changed)
    Q_PROPERTY(QString requestError READ requestError NOTIFY changed)
    Q_PROPERTY(QString conversationId READ conversationId NOTIFY changed)
    Q_PROPERTY(QVariantList conversations READ conversations NOTIFY changed)
    Q_PROPERTY(QVariantList conversationSearchResults READ conversationSearchResults NOTIFY changed)
    Q_PROPERTY(QVariantList options READ options NOTIFY changed)
    Q_PROPERTY(QVariantMap agentState READ agentState NOTIFY changed)
    Q_PROPERTY(QVariantList models READ models NOTIFY changed)
    Q_PROPERTY(QVariantList modelRoles READ modelRoles NOTIFY changed)
    Q_PROPERTY(QVariantList skills READ skills NOTIFY changed)
    Q_PROPERTY(QVariantList mcpServers READ mcpServers NOTIFY changed)
    Q_PROPERTY(QVariantList controls READ controls NOTIFY changed)
    Q_PROPERTY(QVariantMap memoryState READ memoryState NOTIFY changed)
    Q_PROPERTY(QVariantList memories READ memories NOTIFY changed)
    Q_PROPERTY(QVariantList pendingResources READ pendingResources NOTIFY changed)
    Q_PROPERTY(QVariantMap responseMetadata READ responseMetadata NOTIFY changed)
public:
    explicit AgentClient(QObject *parent = nullptr);
    bool busy() const { return m_reply != nullptr; }
    bool actionBusy() const { return m_actionReply != nullptr; }
    bool metadataBusy() const { return m_metadataReply != nullptr; }
    bool conversationSearchBusy() const { return m_conversationSearchReply != nullptr; }
    bool serviceMode() const { return m_serviceMode; }
    QString status() const { return m_status; }
    QString metadataStatus() const { return m_metadataStatus; }
    bool requestFailed() const { return m_requestFailed; }
    bool requestRetryable() const { return m_requestRetryable; }
    QString requestError() const { return m_requestError; }
    QString conversationId() const { return m_conversationId; }
    QVariantList conversations() const { return m_conversations; }
    QVariantList conversationSearchResults() const { return m_conversationSearchResults; }
    QVariantList options() const { return m_options; }
    QVariantMap agentState() const { return m_agentState; }
    QVariantList models() const { return m_models; }
    QVariantList modelRoles() const {
        QVariantList roles;
        roles.reserve(m_modelRoles.size());
        for (const QVariant &value : m_modelRoles) {
            QVariantMap role = value.toMap();
            const QString availabilityKey = QStringLiteral("preferred_available");
            if (role.contains(availabilityKey) && !role.value(availabilityKey).toBool()) {
                const QString configured = role.value(QStringLiteral("preferred_model_id")).toString();
                if (!configured.isEmpty())
                    role.insert(QStringLiteral("configured_preferred_model_id"), configured);
                role.insert(QStringLiteral("preferred_model_id"),
                            role.value(QStringLiteral("fallback_model_id")).toString());
            }
            roles.append(role);
        }
        return roles;
    }
    QVariantList skills() const { return m_skills; }
    QVariantList mcpServers() const { return m_mcpServers; }
    QVariantList controls() const { return m_controls; }
    QVariantMap memoryState() const { return m_memoryState; }
    QVariantList memories() const { return m_memories; }
    QVariantList pendingResources() const { return m_pendingResources; }
    QVariantMap responseMetadata() const { return m_responseMetadata; }
    Q_INVOKABLE virtual void send(const QString &text);
    Q_INVOKABLE void sendWithPendingResources(const QString &text);
    Q_INVOKABLE void addLongTextResource(const QString &name, const QString &text);
    Q_INVOKABLE void addFileResource(const QUrl &fileUrl);
    Q_INVOKABLE int addClipboardResources();
    Q_INVOKABLE bool addClipboardImageResource();
    Q_INVOKABLE void copyDiagnosticsToClipboard();
    Q_INVOKABLE void discardPendingResource(const QString &resourceId);
    Q_INVOKABLE void clearPendingResources();
    Q_INVOKABLE void choose(int index);
    Q_INVOKABLE void cancel();
    Q_INVOKABLE void retryLastRequest();
    Q_INVOKABLE virtual void newChat();
    Q_INVOKABLE void refreshConversations();
    Q_INVOKABLE void searchConversations(const QString &query);
    Q_INVOKABLE void resumeConversation(const QString &conversationId);
    Q_INVOKABLE void renameConversation(const QString &conversationId, const QString &title);
    Q_INVOKABLE void deleteConversation(const QString &conversationId);
    Q_INVOKABLE void exportConversation(const QString &conversationId, const QUrl &fileUrl);
    Q_INVOKABLE void refreshServiceMetadata();
    Q_INVOKABLE void refreshMemory(const QString &query = QString());
    Q_INVOKABLE void setConversationModel(const QString &modelId);
    Q_INVOKABLE void setModelRole(const QString &roleId, const QString &modelId);
    Q_INVOKABLE void setSkillEnabled(const QString &skillId, bool enabled);
    Q_INVOKABLE void setControl(const QString &controlId, const QVariant &value);
    Q_INVOKABLE void setMemoryEnabled(bool enabled);
    Q_INVOKABLE void createMemory(const QString &text, bool pinned = false);
    Q_INVOKABLE void updateMemory(const QString &memoryId, const QString &text, bool pinned);
    Q_INVOKABLE void deleteMemory(const QString &memoryId);
signals:
    void changed();
    void message(const QString &role, const QString &text);
    void delta(const QString &text);
    void toolEvent(const QVariantMap &event);
    void presentationEvent(const QVariantMap &event);
    void responseMetaEvent(const QVariantMap &event);
    void conversationMetadata(const QVariantMap &metadata);
    void resetChat();
protected:
    bool resourceCleanupBusy() const {
        return m_clearPendingResourcesRequested || !m_resourceDeletionQueue.isEmpty();
    }
    void abandonPendingResources() {
        m_pendingResources.clear();
        m_binaryResourceQueue.clear();
        m_resourceDeletionQueue.clear();
        m_clearPendingResourcesRequested = false;
        m_resourceDeletionFailed = false;
        emit changed();
    }
private:
    struct QueuedBinaryResource {
        QString name;
        QString mimeType;
        QByteArray data;
    };

    void requestLegacy(const QString &text);
    void consumeLegacy();
    void ensureServiceConversation(const std::function<void()> &then);
    void loadServiceHistory();
    QVariantMap conversationMetadataForId(const QString &conversationId) const;
    void sendService(const QString &text, bool emitAssistantPlaceholder = true);
    void sendServiceWithResources(const QString &text, const QVariantList &resources);
    void queueBinaryResource(const QString &name, const QString &mimeType, const QByteArray &data);
    void processBinaryResourceQueue();
    void finishBinaryResourceQueueItem();
    void uploadBinaryResource(const QString &conversation, const QString &resourceId, const QByteArray &data);
    void processResourceDeletionQueue();
    void reconnectServiceStream();
    void attachServiceStream(QNetworkReply *reply);
    void consumeService();
    void submitServiceCancel();
    void clearRequestFailure(bool clearLastRequest = false);
    void setRequestFailure(const QString &message, bool retryable);
    void fetchServiceMetadataStep(int step, bool hadError);
    void postServiceAction(const QUrl &url, const QByteArray &body, const std::function<void(QNetworkReply *)> &onSuccess);
    void deleteServiceAction(const QUrl &url, const std::function<void(QNetworkReply *)> &onSuccess);
    QUrl validatedOrigin(const QByteArray &variable, const QString &fallback = QString()) const;
    QNetworkAccessManager m_network;
    QNetworkReply *m_reply = nullptr;
    QNetworkReply *m_actionReply = nullptr;
    QNetworkReply *m_metadataReply = nullptr;
    QNetworkReply *m_conversationSearchReply = nullptr;
    QByteArray m_buffer;
    QString m_user;
    QString m_conversationId;
    QString m_requestId;
    QString m_decisionId;
    QString m_pendingServiceText;
    QString m_lastRequestText;
    QString m_status;
    QString m_metadataStatus;
    QString m_requestError;
    QString m_memoryQuery;
    QVariantList m_conversations;
    QVariantList m_conversationSearchResults;
    QVariantList m_options;
    QVariantMap m_agentState;
    QVariantList m_models;
    QVariantList m_modelRoles;
    QVariantList m_skills;
    QVariantList m_mcpServers;
    QVariantList m_controls;
    QVariantMap m_memoryState;
    QVariantList m_memories;
    QVariantList m_pendingResources;
    QVariantMap m_responseMetadata;
    QList<QueuedBinaryResource> m_binaryResourceQueue;
    QVariantList m_resourceDeletionQueue;
    bool m_clearPendingResourcesRequested = false;
    bool m_resourceDeletionFailed = false;
    bool m_done = false;
    bool m_serviceMode = false;
    bool m_cancelPending = false;
    bool m_staleConversationRetryUsed = false;
    bool m_requestFailed = false;
    bool m_lastRequestHasPendingResources = false;
    bool m_requestRetryable = false;
    int m_lastEventSeq = 0;
    int m_reconnectAttempts = 0;
};

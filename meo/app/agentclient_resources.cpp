#include "agentclient.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkRequest>

namespace {
constexpr int kMaxPendingResources = 16;
}

void AgentClient::addLongTextResource(const QString &name, const QString &text) {
    const QString resourceName = name.trimmed().isEmpty() ? tr("Long paste.txt") : name.trimmed();
    if (!m_serviceMode || busy() || actionBusy() || text.isEmpty()) return;
    if (m_pendingResources.size() >= kMaxPendingResources) {
        m_status = tr("At most %1 resources can be attached to one request.").arg(kMaxPendingResources);
        emit changed();
        return;
    }

    ensureServiceConversation([this, resourceName, text] {
        QUrl base = validatedOrigin("MEO_AI_SERVICE_ENDPOINT");
        if (!base.isValid()) {
            m_status = tr("MEO_AI_SERVICE_ENDPOINT must be a loopback HTTP origin.");
            emit changed();
            return;
        }
        const QString conversation = m_conversationId;
        QUrl url = base;
        url.setPath(QString("/v1/conversations/%1/resources/text").arg(conversation));
        const QJsonObject body{{"name", resourceName}, {"text", text}};
        postServiceAction(
            url,
            QJsonDocument(body).toJson(QJsonDocument::Compact),
            [this, conversation](QNetworkReply *reply) {
                QJsonParseError parseError;
                const auto document = QJsonDocument::fromJson(reply->readAll(), &parseError);
                if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
                    m_status = tr("AgentService returned invalid resource metadata.");
                    return;
                }
                const auto resource = document.object().value("resource").toObject();
                const QString resourceId = resource.value("resource_id").toString();
                if (!resourceId.startsWith("resource:")) {
                    m_status = tr("AgentService returned an invalid resource ID.");
                    return;
                }
                QVariantMap item = resource.toVariantMap();
                item.insert("conversation_id", conversation);
                for (const QVariant &existingValue : m_pendingResources) {
                    if (existingValue.toMap().value("resource_id").toString() == resourceId) {
                        m_status = tr("Resource already attached");
                        return;
                    }
                }
                m_pendingResources.append(item);
                m_status = tr("Long paste attached");
            });
    });
}

void AgentClient::discardPendingResource(const QString &resourceId) {
    const QString id = resourceId.trimmed();
    if (!m_serviceMode || actionBusy() || !id.startsWith("resource:") || id.contains('/')) return;

    int targetIndex = -1;
    QString conversation;
    for (int i = 0; i < m_pendingResources.size(); ++i) {
        const QVariantMap item = m_pendingResources.at(i).toMap();
        if (item.value("resource_id").toString() == id) {
            targetIndex = i;
            conversation = item.value("conversation_id").toString();
            break;
        }
    }
    if (targetIndex < 0 || conversation.isEmpty()) return;

    QUrl base = validatedOrigin("MEO_AI_SERVICE_ENDPOINT");
    if (!base.isValid()) {
        m_status = tr("MEO_AI_SERVICE_ENDPOINT must be a loopback HTTP origin.");
        emit changed();
        return;
    }
    QUrl url = base;
    url.setPath(QString("/v1/conversations/%1/resources/%2").arg(conversation, id));
    deleteServiceAction(url, [this, id](QNetworkReply *) {
        for (int i = m_pendingResources.size() - 1; i >= 0; --i) {
            if (m_pendingResources.at(i).toMap().value("resource_id").toString() == id)
                m_pendingResources.removeAt(i);
        }
        m_status = tr("Attachment removed");
    });
}

void AgentClient::clearPendingResources() {
    if (busy() || actionBusy()) return;
    m_pendingResources.clear();
    m_status = tr("Pending attachments cleared");
    emit changed();
}

void AgentClient::sendWithPendingResources(const QString &text) {
    const QString value = text.trimmed();
    if (value.isEmpty() || busy() || actionBusy() || !m_options.isEmpty()) return;
    if (!m_serviceMode) {
        AgentClient::send(value);
        return;
    }

    m_responseMetadata.clear();
    emit changed();
    emit message("user", value);
    ensureServiceConversation([this, value] {
        QVariantList usable;
        for (const QVariant &entryValue : m_pendingResources) {
            const QVariantMap entry = entryValue.toMap();
            if (entry.value("conversation_id").toString() == m_conversationId &&
                entry.value("state").toString() == "ready" &&
                entry.value("resource_id").toString().startsWith("resource:")) {
                usable.append(entry);
            }
        }
        if (usable.isEmpty())
            sendService(value);
        else
            sendServiceWithResources(value, usable);
    });
}

void AgentClient::sendServiceWithResources(const QString &text, const QVariantList &resources) {
    QUrl base = validatedOrigin("MEO_AI_SERVICE_ENDPOINT");
    if (!base.isValid()) {
        m_status = tr("MEO_AI_SERVICE_ENDPOINT must be a loopback HTTP origin.");
        emit changed();
        return;
    }

    QJsonArray resourceIds;
    for (const QVariant &entryValue : resources) {
        const QString resourceId = entryValue.toMap().value("resource_id").toString();
        if (!resourceId.startsWith("resource:") || resourceId.contains('/')) continue;
        resourceIds.append(resourceId);
    }
    if (resourceIds.isEmpty()) {
        sendService(text);
        return;
    }

    QUrl url = base;
    url.setPath(QString("/v1/conversations/%1/messages").arg(m_conversationId));
    QNetworkRequest request(url);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    const QJsonObject body{{"text", text}, {"resource_ids", resourceIds}};

    m_buffer.clear();
    m_done = false;
    m_requestId.clear();
    m_decisionId.clear();
    m_cancelPending = false;
    m_lastEventSeq = 0;
    m_reconnectAttempts = 0;
    m_options.clear();
    m_pendingServiceText = text;
    // A stale conversation would also invalidate its scoped resources. Refuse
    // the existing automatic no-resource retry instead of silently dropping
    // attachments from the user's request.
    m_staleConversationRetryUsed = true;
    m_status = tr("Receiving…");
    emit message("assistant", "");

    for (int i = m_pendingResources.size() - 1; i >= 0; --i) {
        const QString pendingId = m_pendingResources.at(i).toMap().value("resource_id").toString();
        for (const QJsonValue &sentId : resourceIds) {
            if (sentId.toString() == pendingId) {
                m_pendingResources.removeAt(i);
                break;
            }
        }
    }
    emit changed();
    attachServiceStream(m_network.post(request, QJsonDocument(body).toJson(QJsonDocument::Compact)));
}

#include "agentclient.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkRequest>
#include <QSettings>

namespace {

bool validConversationId(const QString &conversationId) {
    const QString id = conversationId.trimmed();
    return id.startsWith(QStringLiteral("meo:"))
        && id.size() <= 256
        && !id.contains('/')
        && !id.contains('\\');
}

QVariantMap safeConversation(const QJsonObject &object) {
    const QString id = object.value(QStringLiteral("id")).toString().trimmed();
    if (!validConversationId(id)) return {};

    QVariantMap result{
        {QStringLiteral("id"), id},
        {QStringLiteral("conversation_id"), id},
    };

    const QString title = object.value(QStringLiteral("title")).toString().trimmed();
    const QString summary = object.value(QStringLiteral("summary")).toString().trimmed();
    if (!title.isEmpty()) result.insert(QStringLiteral("title"), title.left(240));
    if (!summary.isEmpty()) result.insert(QStringLiteral("summary"), summary.left(1200));

    for (const QString &key : {QStringLiteral("title_is_default"), QStringLiteral("title_is_automatic")}) {
        if (object.value(key).isBool()) result.insert(key, object.value(key).toBool());
    }
    for (const QString &key : {QStringLiteral("created_at"), QStringLiteral("updated_at")}) {
        const QString value = object.value(key).toString().trimmed();
        if (!value.isEmpty()) result.insert(key, value.left(128));
    }
    const QJsonValue messageCount = object.value(QStringLiteral("message_count"));
    if (messageCount.isDouble()) {
        const int count = messageCount.toInt(-1);
        if (count >= 0) result.insert(QStringLiteral("message_count"), count);
    }
    return result;
}

} // namespace

QVariantMap AgentClient::conversationMetadataForId(const QString &conversationId) const {
    for (const QVariant &value : m_conversations) {
        const QVariantMap item = value.toMap();
        if (item.value(QStringLiteral("id")).toString() == conversationId)
            return item;
    }
    return {};
}

void AgentClient::refreshConversations() {
    if (!m_serviceMode || actionBusy()) return;

    QUrl base = validatedOrigin("MEO_AI_SERVICE_ENDPOINT");
    if (!base.isValid()) {
        m_status = tr("MEO_AI_SERVICE_ENDPOINT must be a loopback HTTP origin.");
        emit changed();
        return;
    }

    QUrl url = base;
    url.setPath(QStringLiteral("/v1/conversations"));
    QNetworkRequest request(url);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    if (!busy()) m_status = tr("Refreshing chats…");
    QNetworkReply *reply = m_network.get(request);
    m_actionReply = reply;
    emit changed();

    connect(reply, &QNetworkReply::finished, this, [this, reply] {
        if (m_actionReply != reply) {
            reply->deleteLater();
            return;
        }
        m_actionReply = nullptr;
        const int code = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        QJsonParseError parseError;
        const QJsonDocument document = QJsonDocument::fromJson(reply->readAll(), &parseError);
        if (reply->error() != QNetworkReply::NoError || code != 200
            || parseError.error != QJsonParseError::NoError || !document.isObject()) {
            if (!busy()) m_status = tr("Could not load conversation history.");
            reply->deleteLater();
            emit changed();
            return;
        }

        QVariantList catalog;
        const QJsonArray items = document.object().value(QStringLiteral("conversations")).toArray();
        catalog.reserve(items.size());
        for (const QJsonValue &value : items) {
            if (!value.isObject()) continue;
            const QVariantMap item = safeConversation(value.toObject());
            if (!item.isEmpty()) catalog.append(item);
        }
        m_conversations = catalog;

        const QVariantMap current = conversationMetadataForId(m_conversationId);
        if (!current.isEmpty()) emit conversationMetadata(current);
        if (!busy()) m_status = tr("Ready");
        reply->deleteLater();
        emit changed();
    });
}

void AgentClient::resumeConversation(const QString &conversationId) {
    const QString id = conversationId.trimmed();
    if (!m_serviceMode || busy() || actionBusy() || !m_options.isEmpty()) return;
    if (!validConversationId(id)) {
        m_status = tr("That conversation ID is invalid.");
        emit changed();
        return;
    }
    if (!m_pendingResources.isEmpty() || resourceCleanupBusy() || !m_binaryResourceQueue.isEmpty()) {
        m_status = tr("Send or remove pending attachments before switching conversations.");
        emit changed();
        return;
    }

    const QVariantMap metadata = conversationMetadataForId(id);
    if (metadata.isEmpty()) {
        m_status = tr("That conversation is no longer in the local history. Refresh chats and try again.");
        emit changed();
        return;
    }

    QUrl base = validatedOrigin("MEO_AI_SERVICE_ENDPOINT");
    if (!base.isValid()) {
        m_status = tr("MEO_AI_SERVICE_ENDPOINT must be a loopback HTTP origin.");
        emit changed();
        return;
    }

    QUrl url = base;
    url.setPath(QStringLiteral("/v1/conversations/%1/messages").arg(id));
    QNetworkRequest request(url);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    m_status = tr("Opening conversation…");
    QNetworkReply *reply = m_network.get(request);
    m_actionReply = reply;
    emit changed();

    connect(reply, &QNetworkReply::finished, this, [this, reply, id, metadata] {
        if (m_actionReply != reply) {
            reply->deleteLater();
            return;
        }
        m_actionReply = nullptr;
        const int code = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        QJsonParseError parseError;
        const QJsonDocument document = QJsonDocument::fromJson(reply->readAll(), &parseError);

        if (code == 404) {
            QVariantList remaining;
            for (const QVariant &value : m_conversations) {
                if (value.toMap().value(QStringLiteral("id")).toString() != id)
                    remaining.append(value);
            }
            m_conversations = remaining;
            m_status = tr("That conversation no longer exists.");
        } else if (reply->error() != QNetworkReply::NoError || code != 200
                   || parseError.error != QJsonParseError::NoError || !document.isObject()) {
            m_status = tr("Could not open that conversation.");
        } else {
            const QJsonObject object = document.object();
            if (object.value(QStringLiteral("conversation_id")).toString() != id) {
                m_status = tr("AgentService returned mismatched conversation history.");
            } else {
                m_conversationId = id;
                QSettings().setValue(QStringLiteral("serviceConversationId"), id);
                m_requestId.clear();
                m_decisionId.clear();
                m_pendingServiceText.clear();
                m_cancelPending = false;
                m_staleConversationRetryUsed = false;
                m_lastEventSeq = 0;
                m_reconnectAttempts = 0;
                m_lastRequestHasPendingResources = false;
                m_responseMetadata.clear();
                clearRequestFailure(true);

                emit resetChat();
                const QJsonArray messages = object.value(QStringLiteral("messages")).toArray();
                for (const QJsonValue &value : messages) {
                    if (!value.isObject()) continue;
                    const QJsonObject entry = value.toObject();
                    const QString role = entry.value(QStringLiteral("role")).toString();
                    const QString text = entry.value(QStringLiteral("text")).toString();
                    if ((role == QStringLiteral("user") || role == QStringLiteral("assistant"))
                        && !text.isEmpty()) {
                        emit message(role, text);
                    }
                }
                QVariantMap selectedMetadata = metadata;
                selectedMetadata.insert(QStringLiteral("conversation_id"), id);
                emit conversationMetadata(selectedMetadata);
                m_status = tr("Ready");
            }
        }
        reply->deleteLater();
        emit changed();
    });
}

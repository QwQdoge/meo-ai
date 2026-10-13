#include "agentclient.h"

#include <QBuffer>
#include <QClipboard>
#include <QFile>
#include <QFileInfo>
#include <QGuiApplication>
#include <QImage>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMimeDatabase>
#include <QMimeData>
#include <QNetworkRequest>

namespace {
constexpr int kMaxPendingResources = 16;
constexpr qint64 kMaxLocalResourceBytes = 25 * 1024 * 1024;
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

void AgentClient::addFileResource(const QUrl &fileUrl) {
    if (!m_serviceMode || busy() || actionBusy() || !fileUrl.isLocalFile()) return;
    const QString path = fileUrl.toLocalFile();
    QFileInfo info(path);
    if (!info.exists() || !info.isFile() || info.size() < 0) {
        m_status = tr("The selected attachment is not a readable file.");
        emit changed();
        return;
    }
    if (info.size() > kMaxLocalResourceBytes) {
        m_status = tr("Attachments must be 25 MB or smaller.");
        emit changed();
        return;
    }
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) {
        m_status = tr("The selected attachment could not be opened.");
        emit changed();
        return;
    }
    const QByteArray data = file.readAll();
    if (data.size() != info.size()) {
        m_status = tr("The selected attachment could not be read completely.");
        emit changed();
        return;
    }
    const QString mimeType = QMimeDatabase().mimeTypeForFile(info, QMimeDatabase::MatchContent).name();
    queueBinaryResource(info.fileName(), mimeType, data);
}

bool AgentClient::addClipboardImageResource() {
    if (!m_serviceMode || busy() || actionBusy()) return false;
    QClipboard *clipboard = QGuiApplication::clipboard();
    if (!clipboard || !clipboard->mimeData() || !clipboard->mimeData()->hasImage()) return false;
    const QImage image = clipboard->image();
    if (image.isNull()) return false;
    QByteArray data;
    QBuffer buffer(&data);
    if (!buffer.open(QIODevice::WriteOnly) || !image.save(&buffer, "PNG")) {
        m_status = tr("Clipboard image could not be encoded.");
        emit changed();
        return true;
    }
    if (data.size() > kMaxLocalResourceBytes) {
        m_status = tr("Clipboard image is larger than 25 MB.");
        emit changed();
        return true;
    }
    queueBinaryResource(tr("Clipboard image.png"), QStringLiteral("image/png"), data);
    return true;
}

void AgentClient::queueBinaryResource(const QString &name, const QString &mimeType, const QByteArray &data) {
    if (!m_serviceMode || busy() || actionBusy() || data.isEmpty()) return;
    if (m_pendingResources.size() >= kMaxPendingResources) {
        m_status = tr("At most %1 resources can be attached to one request.").arg(kMaxPendingResources);
        emit changed();
        return;
    }
    if (data.size() > kMaxLocalResourceBytes) {
        m_status = tr("Attachments must be 25 MB or smaller.");
        emit changed();
        return;
    }
    const QString safeName = name.trimmed().isEmpty() ? tr("Attachment") : name.trimmed();
    const QString safeMime = mimeType.trimmed().isEmpty() ? QStringLiteral("application/octet-stream") : mimeType.trimmed();
    const QString kind = safeMime.startsWith(QStringLiteral("image/"), Qt::CaseInsensitive)
        ? QStringLiteral("image")
        : QStringLiteral("attachment");

    ensureServiceConversation([this, safeName, safeMime, kind, data] {
        if (actionBusy()) return;
        QUrl base = validatedOrigin("MEO_AI_SERVICE_ENDPOINT");
        if (!base.isValid()) {
            m_status = tr("MEO_AI_SERVICE_ENDPOINT must be a loopback HTTP origin.");
            emit changed();
            return;
        }
        const QString conversation = m_conversationId;
        QUrl url = base;
        url.setPath(QString("/v1/conversations/%1/resources").arg(conversation));
        QNetworkRequest request(url);
        request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
        request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
        const QJsonObject body{
            {"kind", kind},
            {"name", safeName},
            {"mime_type", safeMime},
            {"size_bytes", data.size()},
        };
        m_status = tr("Preparing attachment…");
        m_actionReply = m_network.post(request, QJsonDocument(body).toJson(QJsonDocument::Compact));
        emit changed();
        connect(m_actionReply, &QNetworkReply::finished, this, [this, conversation, data] {
            QNetworkReply *reply = m_actionReply;
            m_actionReply = nullptr;
            const int code = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
            QJsonParseError parseError;
            const auto document = QJsonDocument::fromJson(reply->readAll(), &parseError);
            if (reply->error() != QNetworkReply::NoError || code < 200 || code >= 300 ||
                parseError.error != QJsonParseError::NoError || !document.isObject()) {
                m_status = code == 413
                    ? tr("Attachment is too large for AgentService.")
                    : tr("Attachment could not be prepared (HTTP %1).").arg(code);
                reply->deleteLater();
                emit changed();
                return;
            }
            const auto resource = document.object().value("resource").toObject();
            const QString resourceId = resource.value("resource_id").toString();
            reply->deleteLater();
            if (!resourceId.startsWith("resource:") || resourceId.contains('/')) {
                m_status = tr("AgentService returned an invalid resource ID.");
                emit changed();
                return;
            }
            uploadBinaryResource(conversation, resourceId, data);
        });
    });
}

void AgentClient::uploadBinaryResource(
    const QString &conversation,
    const QString &resourceId,
    const QByteArray &data
) {
    if (actionBusy() || conversation != m_conversationId) return;
    QUrl base = validatedOrigin("MEO_AI_SERVICE_ENDPOINT");
    if (!base.isValid()) {
        m_status = tr("MEO_AI_SERVICE_ENDPOINT must be a loopback HTTP origin.");
        emit changed();
        return;
    }
    QUrl url = base;
    url.setPath(QString("/v1/conversations/%1/resources/%2/content").arg(conversation, resourceId));
    QNetworkRequest request(url);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/octet-stream");
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    m_status = tr("Uploading attachment…");
    m_actionReply = m_network.put(request, data);
    emit changed();
    connect(m_actionReply, &QNetworkReply::finished, this, [this, conversation, resourceId] {
        QNetworkReply *reply = m_actionReply;
        m_actionReply = nullptr;
        const int code = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        QJsonParseError parseError;
        const auto document = QJsonDocument::fromJson(reply->readAll(), &parseError);
        if (reply->error() != QNetworkReply::NoError || code < 200 || code >= 300 ||
            parseError.error != QJsonParseError::NoError || !document.isObject()) {
            m_status = tr("Attachment upload failed (HTTP %1).").arg(code);
            reply->deleteLater();
            emit changed();
            return;
        }
        const auto resource = document.object().value("resource").toObject();
        if (resource.value("resource_id").toString() != resourceId ||
            resource.value("state").toString() != "ready") {
            m_status = tr("AgentService returned invalid attachment metadata.");
            reply->deleteLater();
            emit changed();
            return;
        }
        QVariantMap item = resource.toVariantMap();
        item.insert("conversation_id", conversation);
        m_pendingResources.append(item);
        m_status = tr("Attachment ready");
        reply->deleteLater();
        emit changed();
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

    clearRequestFailure(true);
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

    clearRequestFailure(true);
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

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
#include <QStringList>

namespace {
constexpr int kMaxPendingResources = 16;
constexpr qint64 kMaxLocalResourceBytes = 25 * 1024 * 1024;
}

void AgentClient::addLongTextResource(const QString &name, const QString &text) {
    const QString resourceName = name.trimmed().isEmpty() ? tr("Long paste.txt") : name.trimmed();
    if (!m_serviceMode || busy() || actionBusy() || text.isEmpty()) return;
    if (m_pendingResources.size() + m_binaryResourceQueue.size() >= kMaxPendingResources) {
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
    // OpenFiles delivers every selected URL synchronously. Do not reject later
    // files merely because the first one already owns the action-reply lane;
    // each validated file joins the private sequential upload queue below.
    if (!m_serviceMode || busy() || !fileUrl.isLocalFile()) return;
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
    if (!m_serviceMode || busy() || data.isEmpty()) return;
    if (m_pendingResources.size() + m_binaryResourceQueue.size() >= kMaxPendingResources) {
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
    m_binaryResourceQueue.append(QueuedBinaryResource{safeName, safeMime, data});
    processBinaryResourceQueue();
}

void AgentClient::processBinaryResourceQueue() {
    if (m_binaryResourceQueue.isEmpty() || busy() || actionBusy()) return;
    if (m_conversationId.isEmpty()) {
        ensureServiceConversation([this] { processBinaryResourceQueue(); });
        return;
    }

    const QueuedBinaryResource item = m_binaryResourceQueue.first();
    const QString kind = item.mimeType.startsWith(QStringLiteral("image/"), Qt::CaseInsensitive)
        ? QStringLiteral("image")
        : QStringLiteral("attachment");
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
        {"name", item.name},
        {"mime_type", item.mimeType},
        {"size_bytes", item.data.size()},
    };
    m_status = tr("Preparing attachment…");
    QNetworkReply *reserveReply = m_network.post(request, QJsonDocument(body).toJson(QJsonDocument::Compact));
    m_actionReply = reserveReply;
    emit changed();

    connect(reserveReply, &QNetworkReply::finished, this, [this, reserveReply, conversation, item] {
        if (m_actionReply != reserveReply) {
            reserveReply->deleteLater();
            return;
        }
        m_actionReply = nullptr;
        const int code = reserveReply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        QJsonParseError parseError;
        const auto document = QJsonDocument::fromJson(reserveReply->readAll(), &parseError);
        if (reserveReply->error() != QNetworkReply::NoError || code < 200 || code >= 300 ||
            parseError.error != QJsonParseError::NoError || !document.isObject()) {
            m_status = code == 413
                ? tr("Attachment is too large for AgentService.")
                : tr("Attachment could not be prepared (HTTP %1).").arg(code);
            reserveReply->deleteLater();
            finishBinaryResourceQueueItem();
            emit changed();
            return;
        }
        const auto resource = document.object().value("resource").toObject();
        const QString resourceId = resource.value("resource_id").toString();
        reserveReply->deleteLater();
        if (!resourceId.startsWith("resource:") || resourceId.contains('/')) {
            m_status = tr("AgentService returned an invalid resource ID.");
            finishBinaryResourceQueueItem();
            emit changed();
            return;
        }
        uploadBinaryResource(conversation, resourceId, item.data);
    });
}

void AgentClient::finishBinaryResourceQueueItem() {
    if (!m_binaryResourceQueue.isEmpty())
        m_binaryResourceQueue.removeFirst();
    processBinaryResourceQueue();
}

void AgentClient::uploadBinaryResource(
    const QString &conversation,
    const QString &resourceId,
    const QByteArray &data
) {
    if (actionBusy() || conversation != m_conversationId) {
        m_status = tr("Attachment upload could not continue.");
        finishBinaryResourceQueueItem();
        emit changed();
        return;
    }
    QUrl base = validatedOrigin("MEO_AI_SERVICE_ENDPOINT");
    if (!base.isValid()) {
        m_status = tr("MEO_AI_SERVICE_ENDPOINT must be a loopback HTTP origin.");
        finishBinaryResourceQueueItem();
        emit changed();
        return;
    }
    QUrl url = base;
    url.setPath(QString("/v1/conversations/%1/resources/%2/content").arg(conversation, resourceId));
    QNetworkRequest request(url);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/octet-stream");
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    m_status = tr("Uploading attachment…");
    QNetworkReply *uploadReply = m_network.put(request, data);
    m_actionReply = uploadReply;
    emit changed();
    connect(uploadReply, &QNetworkReply::finished, this, [this, uploadReply, conversation, resourceId] {
        if (m_actionReply != uploadReply) {
            uploadReply->deleteLater();
            return;
        }
        m_actionReply = nullptr;
        const int code = uploadReply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        QJsonParseError parseError;
        const auto document = QJsonDocument::fromJson(uploadReply->readAll(), &parseError);
        if (uploadReply->error() != QNetworkReply::NoError || code < 200 || code >= 300 ||
            parseError.error != QJsonParseError::NoError || !document.isObject()) {
            m_status = tr("Attachment upload failed (HTTP %1).").arg(code);
            uploadReply->deleteLater();
            finishBinaryResourceQueueItem();
            emit changed();
            return;
        }
        const auto resource = document.object().value("resource").toObject();
        if (resource.value("resource_id").toString() != resourceId ||
            resource.value("state").toString() != "ready") {
            m_status = tr("AgentService returned invalid attachment metadata.");
            uploadReply->deleteLater();
            finishBinaryResourceQueueItem();
            emit changed();
            return;
        }
        QVariantMap item = resource.toVariantMap();
        item.insert("conversation_id", conversation);
        m_pendingResources.append(item);
        m_status = tr("Attachment ready");
        uploadReply->deleteLater();
        finishBinaryResourceQueueItem();
        emit changed();
    });
}

void AgentClient::discardPendingResource(const QString &resourceId) {
    const QString id = resourceId.trimmed();
    if (!m_serviceMode || busy() || actionBusy() || !id.startsWith("resource:") || id.contains('/')) return;

    QVariantMap target;
    for (const QVariant &itemValue : m_pendingResources) {
        const QVariantMap item = itemValue.toMap();
        if (item.value("resource_id").toString() == id) {
            target = item;
            break;
        }
    }
    if (target.isEmpty() || target.value("conversation_id").toString().isEmpty()) return;

    m_resourceDeletionQueue = QVariantList{target};
    m_clearPendingResourcesRequested = false;
    m_resourceDeletionFailed = false;
    processResourceDeletionQueue();
}

void AgentClient::clearPendingResources() {
    if (busy() || actionBusy()) return;
    if (m_pendingResources.isEmpty()) {
        m_status = tr("No pending attachments to clear");
        emit changed();
        return;
    }
    m_resourceDeletionQueue = m_pendingResources;
    m_clearPendingResourcesRequested = true;
    m_resourceDeletionFailed = false;
    processResourceDeletionQueue();
}

void AgentClient::processResourceDeletionQueue() {
    if (busy() || actionBusy()) return;
    if (m_resourceDeletionQueue.isEmpty()) {
        if (m_clearPendingResourcesRequested) {
            m_status = m_resourceDeletionFailed
                ? tr("Some attachments could not be removed.")
                : tr("Pending attachments cleared");
        } else {
            m_status = m_resourceDeletionFailed
                ? tr("Attachment could not be removed")
                : tr("Attachment removed");
        }
        m_clearPendingResourcesRequested = false;
        m_resourceDeletionFailed = false;
        emit changed();
        return;
    }

    const QVariantMap target = m_resourceDeletionQueue.first().toMap();
    const QString id = target.value("resource_id").toString();
    const QString conversation = target.value("conversation_id").toString();
    if (!id.startsWith("resource:") || id.contains('/') || conversation.isEmpty()) {
        m_resourceDeletionFailed = true;
        m_resourceDeletionQueue.removeFirst();
        processResourceDeletionQueue();
        return;
    }

    QUrl base = validatedOrigin("MEO_AI_SERVICE_ENDPOINT");
    if (!base.isValid()) {
        m_resourceDeletionQueue.clear();
        m_clearPendingResourcesRequested = false;
        m_resourceDeletionFailed = false;
        m_status = tr("MEO_AI_SERVICE_ENDPOINT must be a loopback HTTP origin.");
        emit changed();
        return;
    }
    QUrl url = base;
    url.setPath(QString("/v1/conversations/%1/resources/%2").arg(conversation, id));
    QNetworkRequest request(url);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    QNetworkReply *deleteReply = m_network.sendCustomRequest(request, QByteArrayLiteral("DELETE"));
    m_actionReply = deleteReply;
    emit changed();

    connect(deleteReply, &QNetworkReply::finished, this, [this, deleteReply, id] {
        if (m_actionReply != deleteReply) {
            deleteReply->deleteLater();
            return;
        }
        m_actionReply = nullptr;
        const int code = deleteReply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        const bool removed = (deleteReply->error() == QNetworkReply::NoError && code >= 200 && code < 300)
            || code == 404;
        if (removed) {
            for (int i = m_pendingResources.size() - 1; i >= 0; --i) {
                if (m_pendingResources.at(i).toMap().value("resource_id").toString() == id)
                    m_pendingResources.removeAt(i);
            }
        } else {
            m_resourceDeletionFailed = true;
        }
        if (!m_resourceDeletionQueue.isEmpty())
            m_resourceDeletionQueue.removeFirst();
        deleteReply->deleteLater();
        emit changed();
        processResourceDeletionQueue();
    });
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
    QStringList sentResourceIds;
    for (const QVariant &entryValue : resources) {
        const QString resourceId = entryValue.toMap().value("resource_id").toString();
        if (!resourceId.startsWith("resource:") || resourceId.contains('/')) continue;
        resourceIds.append(resourceId);
        sentResourceIds.append(resourceId);
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

    QNetworkReply *messageReply = m_network.post(request, QJsonDocument(body).toJson(QJsonDocument::Compact));
    // Keep attachments pending until AgentService has actually accepted this
    // message and assigned a request id. A rejected/failed POST therefore
    // remains retryable with the exact same resources instead of silently
    // losing them from the composer.
    connect(messageReply, &QNetworkReply::metaDataChanged, this, [this, messageReply, sentResourceIds] {
        const int code = messageReply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        if (code != 200 || messageReply->rawHeader("X-Meo-Request-Id").isEmpty()) return;
        bool removedAny = false;
        for (int i = m_pendingResources.size() - 1; i >= 0; --i) {
            const QString pendingId = m_pendingResources.at(i).toMap().value("resource_id").toString();
            if (sentResourceIds.contains(pendingId)) {
                m_pendingResources.removeAt(i);
                removedAny = true;
            }
        }
        if (removedAny) emit changed();
    });
    emit changed();
    attachServiceStream(messageReply);
}

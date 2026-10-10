#include "agentclient.h"
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkProxy>
#include <QNetworkRequest>
#include <QSettings>
#include <QTimer>
#include <QUrlQuery>
#include <QUuid>

AgentClient::AgentClient(QObject *parent) : QObject(parent) {
    m_network.setProxy(QNetworkProxy::NoProxy);
    m_serviceMode = !qEnvironmentVariableIsEmpty("MEO_AI_SERVICE_ENDPOINT");
    QSettings settings;
    if (m_serviceMode) {
        m_conversationId = settings.value("serviceConversationId").toString();
        m_status = tr("Connect to the local Meo AgentService to start.");
        m_metadataStatus = tr("Not loaded");
        if (!m_conversationId.isEmpty()) {
            QTimer::singleShot(0, this, [this] { loadServiceHistory(); });
        }
    } else {
        m_user = settings.value("sessionId").toString();
        if (!m_user.startsWith("meo:")) {
            m_user = "meo:" + QUuid::createUuid().toString(QUuid::WithoutBraces);
            settings.setValue("sessionId", m_user);
        }
        m_status = tr("Connect to the fork's local Newelle API to start.");
        m_metadataStatus = tr("AgentService metadata is unavailable in legacy mode.");
    }
}

QUrl AgentClient::validatedOrigin(const QByteArray &variable, const QString &fallback) const {
    const QByteArray raw = qgetenv(variable.constData());
    const QUrl base(raw.isEmpty() ? QUrl(fallback) : QUrl(QString::fromUtf8(raw)));
    if (base.scheme() != "http" ||
        (base.host() != "127.0.0.1" && base.host() != "localhost" && base.host() != "::1") ||
        !base.userInfo().isEmpty() || base.hasQuery() || base.hasFragment() ||
        (base.path() != "" && base.path() != "/")) {
        return {};
    }
    return base;
}

void AgentClient::refreshServiceMetadata() {
    if (!m_serviceMode || m_metadataReply) return;
    m_metadataStatus = tr("Refreshing…");
    emit changed();
    fetchServiceMetadataStep(0, false);
}

void AgentClient::fetchServiceMetadataStep(int step, bool hadError) {
    static const QStringList paths{
        QStringLiteral("/v1/agent-state"),
        QStringLiteral("/v1/models"),
        QStringLiteral("/v1/model-roles"),
        QStringLiteral("/v1/skills"),
        QStringLiteral("/v1/mcp-servers"),
    };
    if (step >= paths.size()) {
        if (!hadError) m_metadataStatus = tr("Ready");
        emit changed();
        return;
    }

    QUrl base = validatedOrigin("MEO_AI_SERVICE_ENDPOINT");
    if (!base.isValid()) {
        m_metadataStatus = tr("MEO_AI_SERVICE_ENDPOINT must be a loopback HTTP origin.");
        emit changed();
        return;
    }
    QUrl url = base;
    url.setPath(paths.at(step));
    QNetworkRequest request(url);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    QNetworkReply *reply = m_network.get(request);
    m_metadataReply = reply;
    emit changed();

    connect(reply, &QNetworkReply::finished, this, [this, reply, step, hadError] {
        if (m_metadataReply != reply) {
            reply->deleteLater();
            return;
        }
        m_metadataReply = nullptr;
        bool nextHadError = hadError;
        const int code = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        QJsonParseError parseError;
        const auto document = QJsonDocument::fromJson(reply->readAll(), &parseError);
        if (reply->error() != QNetworkReply::NoError || code != 200 ||
            parseError.error != QJsonParseError::NoError || !document.isObject()) {
            nextHadError = true;
            m_metadataStatus = tr("Metadata refresh incomplete (HTTP %1).").arg(code);
        } else {
            const auto object = document.object();
            if (step == 0) {
                m_agentState = object.toVariantMap();
            } else if (step == 1) {
                m_models = object.value("models").toArray().toVariantList();
            } else if (step == 2) {
                m_modelRoles = object.value("model_roles").toArray().toVariantList();
            } else if (step == 3) {
                m_skills = object.value("skills").toArray().toVariantList();
            } else if (step == 4) {
                m_mcpServers = object.value("mcp_servers").toArray().toVariantList();
            }
        }
        reply->deleteLater();
        emit changed();
        fetchServiceMetadataStep(step + 1, nextHadError);
    });
}

void AgentClient::setModelRole(const QString &roleId, const QString &modelId) {
    if (!m_serviceMode || actionBusy() || roleId.trimmed().isEmpty()) return;
    QUrl base = validatedOrigin("MEO_AI_SERVICE_ENDPOINT");
    if (!base.isValid()) {
        m_status = tr("MEO_AI_SERVICE_ENDPOINT must be a loopback HTTP origin.");
        emit changed();
        return;
    }
    QUrl url = base;
    url.setPath(QString("/v1/model-roles/%1").arg(roleId));
    QJsonObject body;
    if (modelId.trimmed().isEmpty()) body.insert("model_id", QJsonValue::Null);
    else body.insert("model_id", modelId);
    postServiceAction(url, QJsonDocument(body).toJson(QJsonDocument::Compact), [this](QNetworkReply *) {
        m_status = tr("Model role saved");
        QTimer::singleShot(0, this, [this] { refreshServiceMetadata(); });
    });
}

void AgentClient::send(const QString &text) {
    if (busy() || actionBusy() || !m_options.isEmpty() || text.trimmed().isEmpty()) return;
    emit message("user", text);
    if (m_serviceMode) {
        ensureServiceConversation([this, text] { sendService(text); });
    } else {
        requestLegacy(text);
    }
}

void AgentClient::choose(int index) {
    if (index < 0 || index >= m_options.size() || actionBusy()) return;
    if (!m_serviceMode) {
        if (busy()) return;
        m_options.clear();
        requestLegacy(QString("/option %1").arg(index + 1));
        return;
    }
    if (m_requestId.isEmpty() || m_decisionId.isEmpty()) return;
    QUrl base = validatedOrigin("MEO_AI_SERVICE_ENDPOINT");
    if (!base.isValid()) {
        m_status = tr("MEO_AI_SERVICE_ENDPOINT must be a loopback HTTP origin.");
        emit changed();
        return;
    }
    QUrl url = base;
    url.setPath(QString("/v1/requests/%1/decisions/%2").arg(m_requestId, m_decisionId));
    QJsonObject body{{"option_index", index}};
    postServiceAction(url, QJsonDocument(body).toJson(QJsonDocument::Compact), [this](QNetworkReply *) {
        m_options.clear();
        m_decisionId.clear();
        m_status = tr("Running tool…");
        emit changed();
    });
}

void AgentClient::cancel() {
    if (!m_serviceMode || actionBusy()) return;
    if (m_requestId.isEmpty()) {
        if (!busy()) return;
        m_cancelPending = true;
        m_status = tr("Stopping…");
        emit changed();
        return;
    }
    submitServiceCancel();
}

void AgentClient::submitServiceCancel() {
    if (!m_serviceMode || actionBusy() || m_requestId.isEmpty()) return;
    m_cancelPending = false;
    QUrl base = validatedOrigin("MEO_AI_SERVICE_ENDPOINT");
    if (!base.isValid()) {
        m_status = tr("MEO_AI_SERVICE_ENDPOINT must be a loopback HTTP origin.");
        emit changed();
        return;
    }
    QUrl url = base;
    url.setPath(QString("/v1/requests/%1/cancel").arg(m_requestId));
    postServiceAction(url, QByteArray("{}"), [this](QNetworkReply *) {
        m_options.clear();
        m_decisionId.clear();
        if (!m_done) m_status = tr("Stopping…");
        emit changed();
    });
}

void AgentClient::newChat() {
    if (busy() || actionBusy() || !m_options.isEmpty()) return;
    emit resetChat();
    if (!m_serviceMode) {
        requestLegacy("/new");
        return;
    }
    m_conversationId.clear();
    m_requestId.clear();
    m_decisionId.clear();
    m_pendingServiceText.clear();
    m_cancelPending = false;
    m_staleConversationRetryUsed = false;
    m_lastEventSeq = 0;
    m_reconnectAttempts = 0;
    QSettings().remove("serviceConversationId");
    ensureServiceConversation([this] {
        m_status = tr("Ready");
        emit changed();
    });
}

void AgentClient::ensureServiceConversation(const std::function<void()> &then) {
    if (!m_conversationId.isEmpty()) {
        then();
        return;
    }
    QUrl base = validatedOrigin("MEO_AI_SERVICE_ENDPOINT");
    if (!base.isValid()) {
        m_status = tr("MEO_AI_SERVICE_ENDPOINT must be a loopback HTTP origin.");
        emit changed();
        return;
    }
    QUrl url = base;
    url.setPath("/v1/conversations");
    QNetworkRequest request(url);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    m_status = tr("Creating conversation…");
    m_actionReply = m_network.post(request, QByteArray());
    emit changed();
    connect(m_actionReply, &QNetworkReply::finished, this, [this, then] {
        QNetworkReply *reply = m_actionReply;
        m_actionReply = nullptr;
        const int code = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        const auto document = QJsonDocument::fromJson(reply->readAll());
        if (reply->error() != QNetworkReply::NoError || code < 200 || code >= 300 || !document.isObject()) {
            m_status = tr("Meo AgentService unavailable while creating a conversation.");
        } else {
            m_conversationId = document.object().value("conversation_id").toString();
            if (m_conversationId.isEmpty()) {
                m_status = tr("AgentService returned an invalid conversation.");
            } else {
                QSettings().setValue("serviceConversationId", m_conversationId);
                then();
            }
        }
        reply->deleteLater();
        emit changed();
    });
}

void AgentClient::loadServiceHistory() {
    if (!m_serviceMode || m_conversationId.isEmpty() || actionBusy() || busy()) return;
    QUrl base = validatedOrigin("MEO_AI_SERVICE_ENDPOINT");
    if (!base.isValid()) {
        m_status = tr("MEO_AI_SERVICE_ENDPOINT must be a loopback HTTP origin.");
        emit changed();
        return;
    }

    const QString expectedConversation = m_conversationId;
    QUrl url = base;
    url.setPath(QString("/v1/conversations/%1/messages").arg(expectedConversation));
    QNetworkRequest request(url);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    m_status = tr("Restoring conversation…");
    m_actionReply = m_network.get(request);
    emit changed();

    connect(m_actionReply, &QNetworkReply::finished, this, [this, expectedConversation] {
        QNetworkReply *reply = m_actionReply;
        m_actionReply = nullptr;
        const int code = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        const auto document = QJsonDocument::fromJson(reply->readAll());

        if (code == 404) {
            if (m_conversationId == expectedConversation) {
                m_conversationId.clear();
                QSettings().remove("serviceConversationId");
                emit resetChat();
            }
            m_status = tr("The previous conversation no longer exists. A new one will be created when you send a message.");
        } else if (reply->error() != QNetworkReply::NoError || code != 200 || !document.isObject()) {
            m_status = tr("Could not restore the previous conversation.");
        } else {
            const auto object = document.object();
            const QString returnedConversation = object.value("conversation_id").toString();
            if (returnedConversation != expectedConversation || m_conversationId != expectedConversation) {
                m_status = tr("AgentService returned mismatched conversation history.");
            } else {
                const auto items = object.value("messages").toArray();
                emit resetChat();
                for (const auto &value : items) {
                    if (!value.isObject()) continue;
                    const auto entry = value.toObject();
                    const QString role = entry.value("role").toString();
                    const QString text = entry.value("text").toString();
                    if ((role == "user" || role == "assistant") && !text.isEmpty())
                        emit message(role, text);
                }
                m_status = tr("Ready");
            }
        }
        reply->deleteLater();
        emit changed();
    });
}

void AgentClient::sendService(const QString &text, bool emitAssistantPlaceholder) {
    QUrl base = validatedOrigin("MEO_AI_SERVICE_ENDPOINT");
    if (!base.isValid()) {
        m_status = tr("MEO_AI_SERVICE_ENDPOINT must be a loopback HTTP origin.");
        emit changed();
        return;
    }
    QUrl url = base;
    url.setPath(QString("/v1/conversations/%1/messages").arg(m_conversationId));
    QNetworkRequest request(url);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    QJsonObject body{{"text", text}};
    if (emitAssistantPlaceholder) {
        m_pendingServiceText = text;
        m_staleConversationRetryUsed = false;
    }
    m_buffer.clear();
    m_done = false;
    m_requestId.clear();
    m_decisionId.clear();
    m_cancelPending = false;
    m_lastEventSeq = 0;
    m_reconnectAttempts = 0;
    m_options.clear();
    m_status = tr("Receiving…");
    if (emitAssistantPlaceholder) emit message("assistant", "");
    attachServiceStream(m_network.post(request, QJsonDocument(body).toJson(QJsonDocument::Compact)));
}

void AgentClient::reconnectServiceStream() {
    if (!m_serviceMode || m_done || m_reply || m_requestId.isEmpty()) return;
    QUrl base = validatedOrigin("MEO_AI_SERVICE_ENDPOINT");
    if (!base.isValid()) {
        m_status = tr("MEO_AI_SERVICE_ENDPOINT must be a loopback HTTP origin.");
        emit changed();
        return;
    }
    QUrl url = base;
    url.setPath(QString("/v1/requests/%1/events").arg(m_requestId));
    QUrlQuery query;
    query.addQueryItem("after", QString::number(m_lastEventSeq));
    url.setQuery(query);
    QNetworkRequest request(url);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    m_status = tr("Reconnecting…");
    attachServiceStream(m_network.get(request));
}

void AgentClient::attachServiceStream(QNetworkReply *reply) {
    if (m_reply) {
        reply->abort();
        reply->deleteLater();
        return;
    }
    m_reply = reply;
    m_buffer.clear();
    emit changed();
    connect(reply, &QNetworkReply::metaDataChanged, this, [this, reply] {
        if (m_reply != reply || !m_requestId.isEmpty()) return;
        const auto header = reply->rawHeader("X-Meo-Request-Id");
        if (header.isEmpty()) return;
        m_requestId = QString::fromUtf8(header);
        if (m_cancelPending) submitServiceCancel();
    });
    connect(reply, &QNetworkReply::readyRead, this, &AgentClient::consumeService);
    connect(reply, &QNetworkReply::finished, this, [this, reply] {
        if (m_reply != reply) {
            reply->deleteLater();
            return;
        }
        consumeService();
        const int code = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        const auto networkError = reply->error();
        const QUrl finishedUrl = reply->url();
        reply->deleteLater();
        m_reply = nullptr;

        if (m_done) {
            m_reconnectAttempts = 0;
            emit changed();
            return;
        }

        const QString finishedPath = finishedUrl.path();
        const bool missingConversationBeforeStart = code == 404 && m_requestId.isEmpty()
            && finishedPath.startsWith("/v1/conversations/") && finishedPath.endsWith("/messages");
        if (missingConversationBeforeStart) {
            m_conversationId.clear();
            QSettings().remove("serviceConversationId");
            m_requestId.clear();
            m_decisionId.clear();
            m_options.clear();
            m_reconnectAttempts = 0;

            if (m_cancelPending) {
                m_cancelPending = false;
                m_pendingServiceText.clear();
                m_staleConversationRetryUsed = false;
                m_status = tr("Stopped");
                emit changed();
                return;
            }

            if (!m_staleConversationRetryUsed && !m_pendingServiceText.isEmpty()) {
                m_staleConversationRetryUsed = true;
                const QString retryText = m_pendingServiceText;
                m_status = tr("The previous conversation expired. Creating a new one…");
                emit changed();
                ensureServiceConversation([this, retryText] { sendService(retryText, false); });
                return;
            }

            m_pendingServiceText.clear();
            m_staleConversationRetryUsed = false;
            m_status = tr("The conversation could not be recovered. Send the message again to start a new chat.");
            emit changed();
            return;
        }

        if (code == 404) {
            m_requestId.clear();
            m_decisionId.clear();
            m_options.clear();
            m_pendingServiceText.clear();
            m_cancelPending = false;
            m_staleConversationRetryUsed = false;
            m_reconnectAttempts = 0;
            m_status = tr("The previous request no longer exists. You can start a new request.");
            emit changed();
            return;
        }

        if (code == 409) {
            m_options.clear();
            m_decisionId.clear();
            m_status = tr("Request event history was lost; stopping the request safely…");
            emit changed();
            submitServiceCancel();
            return;
        }

        const bool retryable = !m_requestId.isEmpty() &&
            (code == 200 || code == 0 || code >= 500 || networkError == QNetworkReply::RemoteHostClosedError);
        if (retryable && m_reconnectAttempts < 3) {
            ++m_reconnectAttempts;
            m_status = tr("Reconnecting…");
            emit changed();
            QTimer::singleShot(100, this, [this] { reconnectServiceStream(); });
            return;
        }

        if (networkError != QNetworkReply::NoError || code != 200) {
            m_status = tr("Meo AgentService unavailable (HTTP %1).").arg(code);
        } else {
            m_status = tr("AgentService stream ended before a terminal request event.");
        }
        m_pendingServiceText.clear();
        m_staleConversationRetryUsed = false;
        m_cancelPending = false;
        emit changed();
    });
}

void AgentClient::consumeService() {
    if (!m_reply) return;
    m_buffer += m_reply->readAll();
    if (m_buffer.size() > 1024 * 1024) {
        m_reply->abort();
        return;
    }
    int end;
    while ((end = m_buffer.indexOf('\n')) >= 0) {
        const auto line = m_buffer.left(end).trimmed();
        m_buffer.remove(0, end + 1);
        if (!line.startsWith("data: ")) continue;
        QJsonParseError error;
        const auto document = QJsonDocument::fromJson(line.mid(6), &error);
        if (error.error != QJsonParseError::NoError || !document.isObject()) {
            m_reply->abort();
            return;
        }
        const auto event = document.object();
        const int sequence = event.value("seq").toInt();
        if (sequence > 0) {
            if (sequence <= m_lastEventSeq) continue;
            m_lastEventSeq = sequence;
        }
        const QString type = event.value("type").toString();
        if (type == "request.started") {
            m_requestId = event.value("request_id").toString();
            m_status = m_cancelPending ? tr("Stopping…") : tr("Receiving…");
            if (m_cancelPending) submitServiceCancel();
        } else if (type == "message.delta") {
            const auto content = event.value("delta").toString();
            if (!content.isEmpty()) emit delta(content);
        } else if (type == "tool.requested") {
            m_requestId = event.value("request_id").toString();
            m_decisionId = event.value("decision_id").toString();
            m_options = event.value("options").toArray().toVariantList();
            if (m_cancelPending) {
                submitServiceCancel();
            } else {
                m_status = tr("Tool needs your decision");
                emit toolEvent(event.toVariantMap());
                emit changed();
            }
        } else if (type == "tool.completed") {
            emit toolEvent(event.toVariantMap());
        } else if (type == "presentation.card") {
            emit presentationEvent(event.toVariantMap());
        } else if (type == "request.completed") {
            m_done = true;
            m_pendingServiceText.clear();
            m_staleConversationRetryUsed = false;
            m_cancelPending = false;
            m_status = tr("Ready");
        } else if (type == "request.cancelled") {
            m_done = true;
            m_pendingServiceText.clear();
            m_staleConversationRetryUsed = false;
            m_cancelPending = false;
            m_options.clear();
            m_decisionId.clear();
            m_status = tr("Stopped");
        } else if (type == "request.failed") {
            m_done = true;
            m_pendingServiceText.clear();
            m_staleConversationRetryUsed = false;
            m_cancelPending = false;
            m_options.clear();
            m_decisionId.clear();
            m_status = event.value("error").toString(tr("Request failed"));
        }
    }
}

void AgentClient::postServiceAction(const QUrl &url, const QByteArray &body, const std::function<void(QNetworkReply *)> &onSuccess) {
    if (m_actionReply) return;
    QNetworkRequest request(url);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    m_actionReply = m_network.post(request, body);
    emit changed();
    connect(m_actionReply, &QNetworkReply::finished, this, [this, onSuccess] {
        QNetworkReply *reply = m_actionReply;
        m_actionReply = nullptr;
        const int code = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        if (reply->error() != QNetworkReply::NoError || code < 200 || code >= 300) {
            m_status = tr("AgentService action was rejected (HTTP %1).").arg(code);
            if (code == 404) {
                m_requestId.clear();
                m_decisionId.clear();
                m_options.clear();
                m_cancelPending = false;
            }
        } else {
            onSuccess(reply);
        }
        reply->deleteLater();
        emit changed();
    });
}

void AgentClient::requestLegacy(const QString &text) {
    const QUrl base = validatedOrigin("MEO_AI_ENDPOINT", "http://127.0.0.1:8080");
    if (!base.isValid()) {
        m_status = tr("MEO_AI_ENDPOINT must be a loopback HTTP origin.");
        emit changed();
        return;
    }
    QUrl url = base;
    url.setPath("/v2/chat/completions");
    QNetworkRequest req(url);
    req.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    req.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    const auto key = qgetenv("MEO_AI_API_KEY");
    if (!key.isEmpty()) req.setRawHeader("Authorization", "Bearer " + key);
    QJsonObject body{{"user", m_user}, {"stream", true}, {"messages", QJsonArray{QJsonObject{{"role", "user"}, {"content", text}}}}};
    m_buffer.clear();
    m_done = false;
    m_status = tr("Receiving…");
    emit message("assistant", "");
    m_reply = m_network.post(req, QJsonDocument(body).toJson(QJsonDocument::Compact));
    emit changed();
    connect(m_reply, &QNetworkReply::readyRead, this, &AgentClient::consumeLegacy);
    connect(m_reply, &QNetworkReply::finished, this, [this] {
        consumeLegacy();
        const int code = m_reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        if (m_reply->error() != QNetworkReply::NoError || code != 200)
            m_status = tr("Local runtime unavailable (HTTP %1). Check the API interface and key.").arg(code);
        else if (!m_done)
            m_status = tr("Stream ended before completion; server work may still be running.");
        else
            m_status = m_options.isEmpty() ? tr("Ready") : tr("Tool needs your decision");
        m_reply->deleteLater();
        m_reply = nullptr;
        emit changed();
    });
}

void AgentClient::consumeLegacy() {
    if (!m_reply) return;
    m_buffer += m_reply->readAll();
    if (m_buffer.size() > 1024 * 1024) {
        m_reply->abort();
        return;
    }
    int end;
    while ((end = m_buffer.indexOf('\n')) >= 0) {
        const auto line = m_buffer.left(end).trimmed();
        m_buffer.remove(0, end + 1);
        if (!line.startsWith("data: ")) continue;
        const auto data = line.mid(6);
        if (data == "[DONE]") {
            m_done = true;
            continue;
        }
        QJsonParseError error;
        const auto document = QJsonDocument::fromJson(data, &error);
        if (error.error != QJsonParseError::NoError) {
            m_reply->abort();
            return;
        }
        const auto choices = document.object().value("choices").toArray();
        if (choices.isEmpty()) continue;
        const auto chunk = choices.at(0).toObject().value("delta").toObject();
        const auto event = chunk.value("meo_event").toObject();
        if (!event.isEmpty()) {
            emit toolEvent(event.toVariantMap());
            if (event.value("type") == "tool_interaction") {
                m_options = event.value("options").toArray().toVariantList();
                emit changed();
            }
        }
        const auto content = chunk.value("content").toString();
        if (!content.isEmpty()) emit delta(content);
    }
}

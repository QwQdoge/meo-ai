#include "agentclient.h"
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSettings>
#include <QNetworkProxy>
#include <QUuid>

AgentClient::AgentClient(QObject *parent) : QObject(parent) {
    m_network.setProxy(QNetworkProxy::NoProxy);
    QSettings settings;
    m_user = settings.value("sessionId").toString();
    if (!m_user.startsWith("meo:")) {
        m_user = "meo:" + QUuid::createUuid().toString(QUuid::WithoutBraces);
        settings.setValue("sessionId", m_user);
    }
    m_status = tr("Connect to the fork's local Newelle API to start.");
}
void AgentClient::send(const QString &text) {
    if (busy() || !m_options.isEmpty() || text.trimmed().isEmpty()) return;
    emit message("user", text);
    request(text);
}
void AgentClient::choose(int index) {
    if (busy() || index < 0 || index >= m_options.size()) return;
    // Current v2 command API takes one-based indices. Never auto-select.
    m_options.clear();
    request(QString("/option %1").arg(index + 1));
}
void AgentClient::newChat() {
    if (busy() || !m_options.isEmpty()) return;
    emit resetChat();
    request("/new");
}
void AgentClient::request(const QString &text) {
    const QUrl base(qEnvironmentVariable("MEO_AI_ENDPOINT", "http://127.0.0.1:8080"));
    if (base.scheme() != "http" || (base.host() != "127.0.0.1" && base.host() != "localhost" && base.host() != "::1") || !base.userInfo().isEmpty() || base.hasQuery() || base.hasFragment() || (base.path() != "" && base.path() != "/")) {
        m_status = tr("MEO_AI_ENDPOINT must be a loopback HTTP origin.");
        emit changed(); return;
    }
    QUrl url = base; url.setPath("/v2/chat/completions");
    QNetworkRequest req(url);
    req.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    req.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    const auto key = qgetenv("MEO_AI_API_KEY");
    if (!key.isEmpty()) req.setRawHeader("Authorization", "Bearer " + key);
    QJsonObject body{{"user", m_user}, {"stream", true}, {"messages", QJsonArray{QJsonObject{{"role", "user"}, {"content", text}}}}};
    m_buffer.clear(); m_done = false;
    m_status = tr("Receiving…");
    emit message("assistant", "");
    m_reply = m_network.post(req, QJsonDocument(body).toJson(QJsonDocument::Compact));
    emit changed();
    connect(m_reply, &QNetworkReply::readyRead, this, &AgentClient::consume);
    connect(m_reply, &QNetworkReply::finished, this, [this] {
        consume();
        const int code = m_reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        if (m_reply->error() != QNetworkReply::NoError || code != 200)
            m_status = tr("Local runtime unavailable (HTTP %1). Check the API interface and key.").arg(code);
        else if (!m_done)
            m_status = tr("Stream ended before completion; server work may still be running.");
        else m_status = m_options.isEmpty() ? tr("Ready") : tr("Tool needs your decision");
        m_reply->deleteLater(); m_reply = nullptr;
        emit changed();
    });
}
void AgentClient::consume() {
    m_buffer += m_reply->readAll();
    if (m_buffer.size() > 1024 * 1024) {
        m_reply->abort(); return;
    }
    int end;
    while ((end = m_buffer.indexOf('\n')) >= 0) {
        const auto line = m_buffer.left(end).trimmed(); m_buffer.remove(0, end + 1);
        if (!line.startsWith("data: ")) continue;
        const auto data = line.mid(6);
        if (data == "[DONE]") { m_done = true; continue; }
        QJsonParseError error;
        const auto document = QJsonDocument::fromJson(data, &error);
        if (error.error != QJsonParseError::NoError) { m_reply->abort(); return; }
        const auto choices = document.object().value("choices").toArray();
        if (choices.isEmpty()) continue;
        const auto chunk = choices.at(0).toObject().value("delta").toObject();
        const auto event = chunk.value("meo_event").toObject();
        if (!event.isEmpty()) {
            emit toolEvent(event.toVariantMap());
            if (event.value("type") == "tool_interaction") {
                m_options = event.value("options").toArray().toVariantList(); emit changed();
            }
        }
        const auto content = chunk.value("content").toString();
        if (!content.isEmpty()) emit delta(content);
    }
}

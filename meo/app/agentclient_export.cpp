#include "agentclient.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkRequest>
#include <QSaveFile>

namespace {

QString markdownHeading(const QString &role) {
    return role == QStringLiteral("user")
        ? AgentClient::tr("You")
        : AgentClient::tr("Meo AI");
}

QString safeExportTitle(const QVariantMap &metadata) {
    const QString title = metadata.value(QStringLiteral("title")).toString().trimmed();
    return title.isEmpty() ? AgentClient::tr("Meo AI conversation") : title;
}

QString markdownDocument(const QString &title, const QJsonArray &messages) {
    QString output = QStringLiteral("# %1\n\n").arg(title);
    output += AgentClient::tr("Exported from Meo AI") + QStringLiteral("\n\n");
    for (const QJsonValue &value : messages) {
        if (!value.isObject()) continue;
        const QJsonObject entry = value.toObject();
        const QString role = entry.value(QStringLiteral("role")).toString();
        const QString text = entry.value(QStringLiteral("text")).toString();
        if ((role != QStringLiteral("user") && role != QStringLiteral("assistant"))
            || text.trimmed().isEmpty()) {
            continue;
        }
        output += QStringLiteral("## %1\n\n%2\n\n")
                      .arg(markdownHeading(role), text.trimmed());
    }
    return output;
}

} // namespace

void AgentClient::exportConversation(const QString &conversationId, const QUrl &fileUrl) {
    const QString id = conversationId.trimmed();
    if (!m_serviceMode || busy() || actionBusy()) return;
    if (id.isEmpty() || conversationMetadataForId(id).isEmpty()) {
        m_status = tr("That conversation is no longer available.");
        emit changed();
        return;
    }
    if (!fileUrl.isLocalFile() || fileUrl.toLocalFile().isEmpty()) {
        m_status = tr("Choose a local file for the export.");
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
    m_status = tr("Exporting conversation…");
    QNetworkReply *reply = m_network.get(request);
    m_actionReply = reply;
    emit changed();

    connect(reply, &QNetworkReply::finished, this, [this, reply, id, fileUrl] {
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
            m_status = code == 404
                ? tr("That conversation no longer exists.")
                : tr("Could not export that conversation.");
            reply->deleteLater();
            emit changed();
            return;
        }

        const QJsonObject object = document.object();
        if (object.value(QStringLiteral("conversation_id")).toString() != id) {
            m_status = tr("AgentService returned mismatched conversation history.");
            reply->deleteLater();
            emit changed();
            return;
        }

        QVariantMap metadata = conversationMetadataForId(id);
        if (metadata.isEmpty()) {
            for (const QVariant &value : m_conversationSearchResults) {
                const QVariantMap candidate = value.toMap();
                if (candidate.value(QStringLiteral("id")).toString() == id) {
                    metadata = candidate;
                    break;
                }
            }
        }
        const QString markdown = markdownDocument(
            safeExportTitle(metadata),
            object.value(QStringLiteral("messages")).toArray());

        QSaveFile file(fileUrl.toLocalFile());
        if (!file.open(QIODevice::WriteOnly | QIODevice::Text)
            || file.write(markdown.toUtf8()) < 0
            || !file.commit()) {
            m_status = tr("Could not write the export file.");
        } else {
            m_status = tr("Conversation exported.");
        }
        reply->deleteLater();
        emit changed();
    });
}

#include "agentclient.h"

#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkReply>
#include <QTimer>

void AgentClient::setSkillEnabled(const QString &skillId, bool enabled)
{
    const QString id = skillId.trimmed();
    if (!m_serviceMode || actionBusy() || id.isEmpty() || id.contains(QLatin1Char('/')))
        return;

    QUrl base = validatedOrigin("MEO_AI_SERVICE_ENDPOINT");
    if (!base.isValid()) {
        m_status = tr("MEO_AI_SERVICE_ENDPOINT must be a loopback HTTP origin.");
        emit changed();
        return;
    }

    QUrl url = base;
    url.setPath(QStringLiteral("/v1/skills/%1").arg(id));
    const QJsonObject body{{QStringLiteral("enabled"), enabled}};
    postServiceAction(url, QJsonDocument(body).toJson(QJsonDocument::Compact),
                      [this](QNetworkReply *) {
        m_status = tr("Skill setting saved");
        QTimer::singleShot(0, this, [this] { refreshServiceMetadata(); });
    });
}

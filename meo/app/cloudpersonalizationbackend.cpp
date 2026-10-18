#include "cloudpersonalizationbackend.h"

#include <QDBusArgument>
#include <QDBusConnection>
#include <QDBusInterface>
#include <QDBusReply>
#include <QDBusVariant>
#include <QTimer>

namespace {
const QString kService = QStringLiteral("org.meo.Accounts1");
const QString kPath = QStringLiteral("/org/meo/Accounts1");
const QString kInterface = QStringLiteral("org.meo.Accounts1");
const QString kClient = QStringLiteral("org.meo.MeoAI");

QVariant unpack(const QVariant &value)
{
    if (value.metaType().id() == qMetaTypeId<QDBusVariant>())
        return value.value<QDBusVariant>().variant();
    return value;
}

QVariantMap asMap(const QVariant &value)
{
    const QVariant unwrapped = unpack(value);
    if (unwrapped.metaType().id() == qMetaTypeId<QDBusArgument>())
        return qdbus_cast<QVariantMap>(unwrapped.value<QDBusArgument>());
    return unwrapped.toMap();
}

QVariantList asList(const QVariant &value)
{
    const QVariant unwrapped = unpack(value);
    if (unwrapped.metaType().id() == qMetaTypeId<QDBusArgument>())
        return qdbus_cast<QVariantList>(unwrapped.value<QDBusArgument>());
    return unwrapped.toList();
}
}

CloudPersonalizationBackend::CloudPersonalizationBackend(QObject *parent)
    : QObject(parent)
{
    QDBusConnection::sessionBus().connect(
        kService, kPath, kInterface, QStringLiteral("requestChanged"),
        this, SLOT(requestChanged(QString,QString,QVariantMap)));
    QDBusConnection::sessionBus().connect(
        kService, kPath, kInterface, QStringLiteral("accountChanged"),
        this, SLOT(accountChanged()));
    QTimer::singleShot(0, this, &CloudPersonalizationBackend::accountChanged);
}

void CloudPersonalizationBackend::accountChanged()
{
    QDBusInterface broker(kService, kPath, kInterface, QDBusConnection::sessionBus());
    const QDBusReply<QVariantMap> current = broker.call(QStringLiteral("GetStatus"));
    const bool signedIn = current.isValid()
        && current.value().value(QStringLiteral("signedIn")).toBool();
    if (!signedIn) {
        m_activeId.clear();
        m_activeAction.clear();
        m_busy = false;
        m_settings.clear();
        m_memories.clear();
        m_status = tr("Sign in to Meo Account to sync personal instructions and memory.");
    }
    m_signedIn = signedIn;
    emit changed();
    if (signedIn && !m_busy) refresh();
}

void CloudPersonalizationBackend::fail(const QString &message)
{
    m_busy = false;
    m_activeId.clear();
    m_activeAction.clear();
    m_status = message;
    emit changed();
}

bool CloudPersonalizationBackend::start(const QString &action, const QVariantMap &arguments)
{
    QDBusInterface broker(kService, kPath, kInterface, QDBusConnection::sessionBus());
    if (!broker.isValid()) {
        fail(tr("Meo Account service is unavailable."));
        return false;
    }
    const QDBusReply<QString> reply = broker.call(
        QStringLiteral("StartAiPersonalizationOperation"), kClient, action, arguments);
    if (!reply.isValid() || reply.value().isEmpty()) {
        fail(tr("Meo Account did not authorize cloud personalization."));
        return false;
    }
    m_activeId = reply.value();
    m_activeAction = action;
    m_busy = true;
    m_status = tr("Synchronizing your Meo AI settings…");
    emit changed();
    // A response can complete before the synchronous D-Bus call returns.
    inspect(m_activeId);
    return true;
}

void CloudPersonalizationBackend::inspect(const QString &requestId)
{
    if (requestId.isEmpty() || requestId != m_activeId) return;
    QDBusInterface broker(kService, kPath, kInterface, QDBusConnection::sessionBus());
    const QDBusReply<QVariantMap> reply = broker.call(QStringLiteral("GetRequest"), requestId);
    if (!reply.isValid()) {
        fail(tr("Account refused access to this private cloud result."));
        return;
    }

    const QVariantMap result = reply.value();
    const QString state = result.value(QStringLiteral("state")).toString();
    if (state != QStringLiteral("completed")) {
        if (state == QStringLiteral("failed") || state == QStringLiteral("denied")
            || state == QStringLiteral("expired")) {
            fail(result.value(QStringLiteral("error"))
                     .toString().left(256).isEmpty()
                     ? tr("The cloud request failed.")
                     : result.value(QStringLiteral("error")).toString().left(256));
        }
        return;
    }
    const QString action = m_activeAction;
    const QVariantMap data = asMap(result.value(QStringLiteral("data")));
    m_activeId.clear();
    m_activeAction.clear();
    m_busy = false;

    if (action == QStringLiteral("settings.get")) {
        m_settings = asMap(data.value(QStringLiteral("settings")));
        if (m_settings.isEmpty()) {
            fail(tr("The account settings response was invalid."));
            return;
        }
        start(QStringLiteral("memories.list"),
              {{QStringLiteral("archived"), m_archived}});
        return;
    }

    if (action == QStringLiteral("memories.list")) {
        m_memories.clear();
        for (const QVariant &value : asList(data.value(QStringLiteral("memories"))))
            m_memories.append(asMap(value));
        m_status = tr("Cloud personalization is synchronized.");
        emit changed();
        return;
    }

    if (action == QStringLiteral("settings.update")
        || action.startsWith(QStringLiteral("memories."))) {
        refresh(m_archived);
        return;
    }
    m_status = tr("Cloud request completed.");
    emit changed();
}

void CloudPersonalizationBackend::requestChanged(const QString &requestId,
                                                 const QString &state, const QVariantMap &result)
{
    Q_UNUSED(result)
    if (requestId != m_activeId) return;
    if (state == QStringLiteral("completed") || state == QStringLiteral("failed")
        || state == QStringLiteral("denied") || state == QStringLiteral("expired"))
        inspect(requestId);
}

void CloudPersonalizationBackend::refresh(bool archived)
{
    if (m_busy || !m_signedIn) return;
    m_archived = archived;
    start(QStringLiteral("settings.get"), {});
}

void CloudPersonalizationBackend::saveSettings(const QString &instructions, bool enabled)
{
    if (m_busy || !m_signedIn || m_settings.isEmpty() || instructions.size() > 5000) return;
    start(QStringLiteral("settings.update"),
          {{QStringLiteral("expectedVersion"), m_settings.value(QStringLiteral("version"))},
           {QStringLiteral("personalInstructions"), instructions},
           {QStringLiteral("memoryEnabled"), enabled}});
}

void CloudPersonalizationBackend::addMemory(const QString &content)
{
    if (m_busy || !m_signedIn || content.trimmed().isEmpty() || content.size() > 2000) return;
    start(QStringLiteral("memories.create"),
          {{QStringLiteral("kind"), QStringLiteral("fact")},
           {QStringLiteral("content"), content.trimmed()}});
}

void CloudPersonalizationBackend::updateMemory(const QString &id, int version,
                                               const QString &content)
{
    if (m_busy || !m_signedIn || content.trimmed().isEmpty() || content.size() > 2000) return;
    start(QStringLiteral("memories.update"),
          {{QStringLiteral("id"), id}, {QStringLiteral("expectedVersion"), version},
           {QStringLiteral("content"), content.trimmed()}});
}

void CloudPersonalizationBackend::setMemoryEnabled(const QString &id, int version, bool enabled)
{
    if (m_busy || !m_signedIn) return;
    start(QStringLiteral("memories.update"),
          {{QStringLiteral("id"), id}, {QStringLiteral("expectedVersion"), version},
           {QStringLiteral("enabled"), enabled}});
}

void CloudPersonalizationBackend::archiveMemory(const QString &id, int version, bool archived)
{
    if (m_busy || !m_signedIn) return;
    start(QStringLiteral("memories.update"),
          {{QStringLiteral("id"), id}, {QStringLiteral("expectedVersion"), version},
           {QStringLiteral("archived"), archived}});
}

void CloudPersonalizationBackend::deleteMemory(const QString &id)
{
    if (m_busy || !m_signedIn) return;
    start(QStringLiteral("memories.delete"), {{QStringLiteral("id"), id}});
}

#include "accountaibackend.h"

#include <QDBusArgument>
#include <QDBusConnection>
#include <QDBusInterface>
#include <QDBusReply>
#include <QDesktopServices>
#include <QSettings>
#include <QTimer>
#include <QUrl>

namespace
{
const QString kService = QStringLiteral("org.meo.Accounts1");
const QString kPath = QStringLiteral("/org/meo/Accounts1");
const QString kInterface = QStringLiteral("org.meo.Accounts1");
const QString kClientId = QStringLiteral("org.meo.MeoAI");

QVariantMap mapValue(const QVariant &value)
{
    if (value.metaType().id() == qMetaTypeId<QDBusArgument>())
        return qdbus_cast<QVariantMap>(value.value<QDBusArgument>());
    return value.toMap();
}

QVariantMap normalizedConnection(const QVariant &value)
{
    QVariantMap connection = mapValue(value);
    if (connection.isEmpty())
        return {};

    // Account intentionally owns the nested permission object. Project the one
    // display-safe bit the QML surface needs instead of teaching views about
    // the broker's storage schema (and never copy a credential into this map).
    const QVariantMap automatic = mapValue(connection.value(QStringLiteral("automaticInference")));
    connection.insert(QStringLiteral("automaticInferenceEnabled"),
                      automatic.value(QStringLiteral("enabled")).toBool());
    return connection;
}

QString displayName(const QVariantMap &connection)
{
    const QString name = connection.value(QStringLiteral("displayName")).toString().trimmed();
    return name.isEmpty() ? connection.value(QStringLiteral("provider")).toString() : name;
}

QUrl accountPageUrl(const QString &page)
{
    const QString normalized = page.trimmed().toLower();
    if (normalized == QLatin1String("profile"))
        return QUrl(QStringLiteral("https://account.meoarch.org/settings/profile"));
    if (normalized == QLatin1String("security"))
        return QUrl(QStringLiteral("https://account.meoarch.org/settings/security"));
    if (normalized == QLatin1String("privacy"))
        return QUrl(QStringLiteral("https://account.meoarch.org/settings/privacy"));
    if (normalized == QLatin1String("providers"))
        return QUrl(QStringLiteral("https://account.meoarch.org/services"));
    return QUrl(QStringLiteral("https://account.meoarch.org/"));
}
}

AccountAiBackend::AccountAiBackend(QObject *parent)
    : QObject(parent)
{
    loadPreferences();
    QDBusConnection::sessionBus().connect(
        kService, kPath, kInterface, QStringLiteral("accountChanged"),
        this, SLOT(handleAccountChanged()));
    QDBusConnection::sessionBus().connect(
        kService, kPath, kInterface, QStringLiteral("requestChanged"),
        this, SLOT(handleRequestChanged(QString,QString,QVariantMap)));
    QTimer::singleShot(0, this, &AccountAiBackend::refresh);
}

void AccountAiBackend::loadPreferences()
{
    QSettings settings;
    settings.beginGroup(QStringLiteral("AccountAI"));
    m_selectedConnectionId = settings.value(QStringLiteral("connectionId")).toString();
    m_selectedModelId = settings.value(QStringLiteral("modelId")).toString();
    settings.endGroup();
}

void AccountAiBackend::savePreferences() const
{
    QSettings settings;
    settings.beginGroup(QStringLiteral("AccountAI"));
    settings.setValue(QStringLiteral("connectionId"), m_selectedConnectionId);
    settings.setValue(QStringLiteral("modelId"), m_selectedModelId);
    settings.endGroup();
}

void AccountAiBackend::setStatus(const QString &status)
{
    if (m_status == status)
        return;
    m_status = status;
    emit changed();
}

void AccountAiBackend::setBusy(bool busy)
{
    if (m_busy == busy)
        return;
    m_busy = busy;
    emit changed();
}

void AccountAiBackend::clearAccountIdentity()
{
    m_accountName.clear();
    m_accountEmail.clear();
    m_avatarUrl.clear();
}

QVariantMap AccountAiBackend::connectionById(const QString &connectionId) const
{
    for (const QVariant &value : m_connections) {
        const QVariantMap connection = normalizedConnection(value);
        if (connection.value(QStringLiteral("id")).toString() == connectionId)
            return connection;
    }
    return {};
}

bool AccountAiBackend::modelExists(const QString &modelId) const
{
    for (const QVariant &value : m_models) {
        const QVariantMap model = mapValue(value);
        if (model.value(QStringLiteral("model_id")).toString() == modelId)
            return true;
    }
    return false;
}

void AccountAiBackend::refresh()
{
    QDBusInterface broker(kService, kPath, kInterface, QDBusConnection::sessionBus());
    if (!broker.isValid()) {
        m_serviceAvailable = false;
        m_signedIn = false;
        clearAccountIdentity();
        m_connections.clear();
        m_models.clear();
        m_activeRequestId.clear();
        m_activeRequestKind = RequestKind::None;
        m_discoveryConnectionId.clear();
        m_busy = false;
        m_status = tr("Meo Account service is unavailable.");
        emit changed();
        return;
    }

    const QDBusReply<QVariantMap> statusReply = broker.call(QStringLiteral("GetStatus"));
    const QDBusReply<QVariantList> connectionsReply = broker.call(
        QStringLiteral("ListAvailableLocalAiConnections"), kClientId);

    if (!statusReply.isValid()) {
        m_serviceAvailable = false;
        m_signedIn = false;
        clearAccountIdentity();
        m_connections.clear();
        m_status = tr("Meo Account did not return its current state.");
        emit changed();
        return;
    }

    m_serviceAvailable = true;
    m_signedIn = statusReply.value().value(QStringLiteral("signedIn")).toBool();
    clearAccountIdentity();
    if (m_signedIn) {
        const QDBusReply<QVariantMap> identityReply = broker.call(
            QStringLiteral("GetIdentity"), kClientId);
        if (identityReply.isValid()) {
            const QVariantMap identity = identityReply.value();
            m_accountName = identity.value(QStringLiteral("name")).toString().trimmed();
            m_accountEmail = identity.value(QStringLiteral("email")).toString().trimmed();
            m_avatarUrl = identity.value(QStringLiteral("avatarUrl")).toString().trimmed();
        }
    }

    if (!connectionsReply.isValid()) {
        m_connections.clear();
        m_status = tr("Meo AI is not authorized to use device AI connections.");
        emit changed();
        return;
    }

    m_connections.clear();
    for (const QVariant &value : connectionsReply.value()) {
        const QVariantMap connection = normalizedConnection(value);
        if (!connection.isEmpty())
            m_connections.append(connection);
    }

    if (!m_selectedConnectionId.isEmpty() && connectionById(m_selectedConnectionId).isEmpty()) {
        m_selectedConnectionId.clear();
        m_selectedModelId.clear();
        m_models.clear();
        savePreferences();
    }

    if (m_selectedConnectionId.isEmpty() && m_connections.size() == 1) {
        const QVariantMap only = normalizedConnection(m_connections.first());
        m_selectedConnectionId = only.value(QStringLiteral("id")).toString();
        m_selectedModelId = only.value(QStringLiteral("defaultModel")).toString();
        savePreferences();
    }

    if (!m_signedIn) {
        m_status = tr("Sign in to Meo to sync AI settings and conversations across devices.");
    } else if (m_connections.isEmpty()) {
        m_status = tr("Meo Account is connected. Add an AI provider to start chatting.");
    } else if (!m_selectedConnectionId.isEmpty()) {
        m_status = tr("Preferred connection: %1").arg(displayName(connectionById(m_selectedConnectionId)));
    } else {
        m_status = tr("Choose an AI connection for Meo AI.");
    }
    emit changed();
}

bool AccountAiBackend::signIn()
{
    if (m_busy)
        return false;
    if (m_signedIn)
        return true;

    QDBusInterface broker(kService, kPath, kInterface, QDBusConnection::sessionBus());
    if (!broker.isValid()) {
        setStatus(tr("Meo Account service is unavailable."));
        return false;
    }

    setBusy(true);
    m_activeRequestKind = RequestKind::Authentication;
    m_status = tr("Preparing Meo Account sign-in…");
    emit changed();

    // Account owns the browser OAuth flow, PKCE, token store and callback. Meo AI
    // only asks the registered Account client to connect the system account.
    const QDBusReply<QString> reply = broker.call(
        QStringLiteral("RequestAuthentication"), kClientId,
        QStringLiteral("connect_system"), QVariantMap{});
    if (!reply.isValid() || reply.value().isEmpty()) {
        m_activeRequestKind = RequestKind::None;
        setBusy(false);
        setStatus(tr("Meo AI could not start Account sign-in."));
        return false;
    }

    m_activeRequestId = reply.value();
    const QDBusReply<QVariantMap> current = broker.call(
        QStringLiteral("GetRequest"), m_activeRequestId);
    if (current.isValid() && !current.value().isEmpty()) {
        const QVariantMap snapshot = current.value();
        handleRequestChanged(m_activeRequestId,
                             snapshot.value(QStringLiteral("state")).toString(), snapshot);
    }
    return true;
}

bool AccountAiBackend::openAccountPage(const QString &page)
{
    const QUrl url = accountPageUrl(page);
    if (!url.isValid() || url.scheme() != QLatin1String("https")) {
        setStatus(tr("The Meo Account page is unavailable."));
        return false;
    }
    if (!QDesktopServices::openUrl(url)) {
        setStatus(tr("Your default browser could not open Meo Account."));
        return false;
    }
    return true;
}

bool AccountAiBackend::selectConnection(const QString &connectionId)
{
    const QString id = connectionId.trimmed();
    const QVariantMap connection = connectionById(id);
    if (id.isEmpty() || connection.isEmpty())
        return false;
    if (m_selectedConnectionId == id) {
        if (!m_selectedModelId.isEmpty())
            emit modelActivationRequested(m_selectedConnectionId, m_selectedModelId);
        return true;
    }

    m_selectedConnectionId = id;
    m_selectedModelId = connection.value(QStringLiteral("defaultModel")).toString();
    m_models.clear();
    savePreferences();
    m_status = tr("Preferred connection: %1").arg(displayName(connection));
    emit changed();
    if (!m_selectedModelId.isEmpty())
        emit modelActivationRequested(m_selectedConnectionId, m_selectedModelId);
    return true;
}

bool AccountAiBackend::selectModel(const QString &modelId)
{
    const QString id = modelId.trimmed();
    if (id.isEmpty() || !modelExists(id))
        return false;
    if (m_selectedModelId == id) {
        if (!m_selectedConnectionId.isEmpty())
            emit modelActivationRequested(m_selectedConnectionId, m_selectedModelId);
        return true;
    }
    m_selectedModelId = id;
    savePreferences();
    m_status = tr("Preferred model: %1").arg(id);
    emit changed();
    emit modelActivationRequested(m_selectedConnectionId, m_selectedModelId);
    return true;
}

void AccountAiBackend::discoverModels(const QString &connectionId)
{
    if (m_busy)
        return;
    const QString id = connectionId.trimmed();
    if (connectionById(id).isEmpty()) {
        setStatus(tr("Choose a valid AI connection first."));
        return;
    }

    QDBusInterface broker(kService, kPath, kInterface, QDBusConnection::sessionBus());
    if (!broker.isValid()) {
        setStatus(tr("Meo Account service is unavailable."));
        return;
    }

    setBusy(true);
    m_activeRequestKind = RequestKind::ModelDiscovery;
    m_discoveryConnectionId = id;
    m_models.clear();
    m_status = tr("Discovering provider models…");
    emit changed();

    const QDBusReply<QString> reply = broker.call(
        QStringLiteral("StartLocalAiOperation"), kClientId,
        QStringLiteral("discover_models"), QVariantMap{{QStringLiteral("connectionId"), id}});
    if (!reply.isValid() || reply.value().isEmpty()) {
        m_discoveryConnectionId.clear();
        m_activeRequestKind = RequestKind::None;
        setBusy(false);
        setStatus(tr("Meo AI could not start model discovery. Check its Account permission."));
        return;
    }

    m_activeRequestId = reply.value();

    // The broker may publish an early state (or even an immediate terminal
    // validation failure) before the synchronous D-Bus method returns the
    // request id. Re-read the owned request once so the UI can never remain
    // stuck in Busy merely because that first signal raced the assignment.
    const QDBusReply<QVariantMap> current = broker.call(
        QStringLiteral("GetRequest"), m_activeRequestId);
    if (current.isValid() && !current.value().isEmpty()) {
        const QVariantMap snapshot = current.value();
        handleRequestChanged(m_activeRequestId,
                             snapshot.value(QStringLiteral("state")).toString(), snapshot);
    }
}

void AccountAiBackend::handleRequestChanged(const QString &requestId, const QString &state,
                                            const QVariantMap &result)
{
    if (requestId != m_activeRequestId)
        return;

    const RequestKind kind = m_activeRequestKind;
    const bool terminal = state == QLatin1String("completed")
        || state == QLatin1String("failed")
        || state == QLatin1String("denied")
        || state == QLatin1String("expired");

    if (!terminal) {
        if (kind == RequestKind::Authentication) {
            if (state == QLatin1String("waiting_for_user"))
                setStatus(tr("Continue with Meo Account to sign in."));
            else if (state == QLatin1String("opening_browser"))
                setStatus(tr("Opening Meo Account in your default browser…"));
            else if (state == QLatin1String("waiting_for_callback"))
                setStatus(tr("Finish signing in in your browser."));
        } else if (kind == RequestKind::ModelDiscovery) {
            if (state == QLatin1String("validating_destination"))
                setStatus(tr("Checking the provider destination…"));
            else if (state == QLatin1String("contacting_provider"))
                setStatus(tr("Contacting the provider…"));
        }
        return;
    }

    m_activeRequestId.clear();
    m_activeRequestKind = RequestKind::None;
    setBusy(false);

    if (kind == RequestKind::Authentication) {
        if (state != QLatin1String("completed")) {
            const QString error = result.value(QStringLiteral("error")).toString().trimmed();
            setStatus(error.isEmpty() ? tr("Meo Account sign-in was not completed.") : error);
            return;
        }
        setStatus(tr("Signed in to Meo Account."));
        QTimer::singleShot(0, this, &AccountAiBackend::refresh);
        return;
    }

    if (kind != RequestKind::ModelDiscovery)
        return;

    if (state != QLatin1String("completed")) {
        const QString error = result.value(QStringLiteral("error")).toString().trimmed();
        m_discoveryConnectionId.clear();
        setStatus(error.isEmpty() ? tr("Provider model discovery failed.") : error);
        return;
    }

    QVariantList discovered;
    const QStringList modelIds = result.value(QStringLiteral("models")).toStringList();
    for (const QString &modelId : modelIds) {
        const QString normalized = modelId.trimmed();
        if (!normalized.isEmpty())
            discovered.append(QVariantMap{{QStringLiteral("model_id"), normalized},
                                          {QStringLiteral("label"), normalized}});
    }
    m_models = discovered;
    if (!m_selectedModelId.isEmpty() && !modelExists(m_selectedModelId))
        m_selectedModelId.clear();
    if (m_selectedModelId.isEmpty()) {
        const QVariantMap connection = connectionById(m_discoveryConnectionId);
        const QString defaultModel = connection.value(QStringLiteral("defaultModel")).toString();
        if (!defaultModel.isEmpty() && modelExists(defaultModel))
            m_selectedModelId = defaultModel;
        else if (!m_models.isEmpty())
            m_selectedModelId = mapValue(m_models.first()).value(QStringLiteral("model_id")).toString();
    }
    m_selectedConnectionId = m_discoveryConnectionId;
    m_discoveryConnectionId.clear();
    savePreferences();
    m_status = m_models.isEmpty()
        ? tr("The provider returned no models.")
        : tr("Found %1 provider models.").arg(m_models.size());
    emit changed();
    if (!m_selectedConnectionId.isEmpty() && !m_selectedModelId.isEmpty())
        emit modelActivationRequested(m_selectedConnectionId, m_selectedModelId);
}

void AccountAiBackend::handleAccountChanged()
{
    if (!m_busy)
        refresh();
}

bool AccountAiBackend::openProviderSettings()
{
    // Provider management should feel like part of Meo AI. Until the embedded
    // editor is backed by the Account credential broker, use the Account-owned
    // web surface rather than bouncing users into a separate desktop settings app.
    return openAccountPage(QStringLiteral("providers"));
}

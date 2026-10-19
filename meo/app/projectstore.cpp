#include "projectstore.h"

#include <QDateTime>
#include <QSettings>
#include <QUuid>
#include <QVariantMap>

namespace {
constexpr auto kGroup = "NativeProjects";
constexpr auto kCatalog = "catalog";
constexpr auto kActiveProjectId = "activeProjectId";
}

ProjectStore::ProjectStore(bool persistent, QObject *parent)
    : QObject(parent), m_persistent(persistent)
{
    if (m_persistent)
        load();
}

QVariantList ProjectStore::projects() const
{
    return m_projects;
}

QString ProjectStore::activeProjectId() const
{
    return m_activeProjectId;
}

QString ProjectStore::activeProjectName() const
{
    const int index = indexOf(m_activeProjectId);
    if (index < 0)
        return {};
    return m_projects.at(index).toMap().value(QStringLiteral("name")).toString();
}

QString ProjectStore::createProject(const QString &name)
{
    const QString normalized = name.simplified().left(80);
    if (normalized.isEmpty())
        return {};

    const QString projectId = QUuid::createUuid().toString(QUuid::WithoutBraces);
    const QString now = QDateTime::currentDateTimeUtc().toString(Qt::ISODate);
    QVariantMap project{
        {QStringLiteral("id"), projectId},
        {QStringLiteral("name"), normalized},
        {QStringLiteral("created_at"), now},
        {QStringLiteral("last_opened_at"), now},
    };

    m_projects.prepend(project);
    m_activeProjectId = projectId;
    save();
    emit projectsChanged();
    emit activeProjectChanged();
    return projectId;
}

bool ProjectStore::renameProject(const QString &projectId, const QString &name)
{
    const int index = indexOf(projectId);
    const QString normalized = name.simplified().left(80);
    if (index < 0 || normalized.isEmpty())
        return false;

    QVariantMap project = m_projects.at(index).toMap();
    if (project.value(QStringLiteral("name")).toString() == normalized)
        return true;
    project.insert(QStringLiteral("name"), normalized);
    m_projects[index] = project;
    save();
    emit projectsChanged();
    if (m_activeProjectId == projectId)
        emit activeProjectChanged();
    return true;
}

bool ProjectStore::openProject(const QString &projectId)
{
    const int index = indexOf(projectId);
    if (index < 0)
        return false;

    QVariantMap project = m_projects.at(index).toMap();
    project.insert(QStringLiteral("last_opened_at"),
                   QDateTime::currentDateTimeUtc().toString(Qt::ISODate));
    m_projects.removeAt(index);
    m_projects.prepend(project);

    const bool activeChanged = m_activeProjectId != projectId;
    m_activeProjectId = projectId;
    save();
    emit projectsChanged();
    if (activeChanged)
        emit activeProjectChanged();
    return true;
}

void ProjectStore::closeProject()
{
    if (m_activeProjectId.isEmpty())
        return;
    m_activeProjectId.clear();
    save();
    emit activeProjectChanged();
}

void ProjectStore::load()
{
    QSettings settings;
    settings.beginGroup(QString::fromLatin1(kGroup));
    const QVariantList stored = settings.value(QString::fromLatin1(kCatalog)).toList();
    m_activeProjectId = settings.value(QString::fromLatin1(kActiveProjectId)).toString();
    settings.endGroup();

    m_projects.clear();
    for (const QVariant &entry : stored) {
        const QVariantMap project = entry.toMap();
        const QString id = project.value(QStringLiteral("id")).toString().trimmed();
        const QString name = project.value(QStringLiteral("name")).toString().trimmed();
        if (id.isEmpty() || name.isEmpty())
            continue;
        m_projects.append(project);
    }
    if (indexOf(m_activeProjectId) < 0)
        m_activeProjectId.clear();
}

void ProjectStore::save() const
{
    if (!m_persistent)
        return;
    QSettings settings;
    settings.beginGroup(QString::fromLatin1(kGroup));
    settings.setValue(QString::fromLatin1(kCatalog), m_projects);
    settings.setValue(QString::fromLatin1(kActiveProjectId), m_activeProjectId);
    settings.endGroup();
}

int ProjectStore::indexOf(const QString &projectId) const
{
    if (projectId.isEmpty())
        return -1;
    for (int i = 0; i < m_projects.size(); ++i) {
        if (m_projects.at(i).toMap().value(QStringLiteral("id")).toString() == projectId)
            return i;
    }
    return -1;
}

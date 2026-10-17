#pragma once

#include <QObject>
#include <QVariantList>

class ProjectStore final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QVariantList projects READ projects NOTIFY projectsChanged)
    Q_PROPERTY(QString activeProjectId READ activeProjectId NOTIFY activeProjectChanged)
    Q_PROPERTY(QString activeProjectName READ activeProjectName NOTIFY activeProjectChanged)

public:
    explicit ProjectStore(QObject *parent = nullptr);

    QVariantList projects() const;
    QString activeProjectId() const;
    QString activeProjectName() const;

    Q_INVOKABLE QString createProject(const QString &name);
    Q_INVOKABLE bool openProject(const QString &projectId);
    Q_INVOKABLE void closeProject();

signals:
    void projectsChanged();
    void activeProjectChanged();

private:
    void load();
    void save() const;
    int indexOf(const QString &projectId) const;

    QVariantList m_projects;
    QString m_activeProjectId;
};

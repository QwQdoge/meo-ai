#include "projectstore.h"

#include <QCoreApplication>
#include <QTemporaryDir>
#include <QTest>
#include <QVariantMap>

class ProjectStoreTest final : public QObject
{
    Q_OBJECT

private slots:
    void createOpenAndPersist()
    {
        QTemporaryDir config;
        QVERIFY(config.isValid());
        qputenv("XDG_CONFIG_HOME", config.path().toUtf8());
        QCoreApplication::setOrganizationName(QStringLiteral("MeoArchProjectStoreTests"));
        QCoreApplication::setApplicationName(QStringLiteral("MeoAI"));

        QString firstId;
        QString secondId;
        {
            ProjectStore store;
            QCOMPARE(store.projects().size(), 0);
            QVERIFY(store.createProject(QStringLiteral("   ")).isEmpty());

            firstId = store.createProject(QStringLiteral("  MeoArch   OS  "));
            QVERIFY(!firstId.isEmpty());
            QCOMPARE(store.activeProjectId(), firstId);
            QCOMPARE(store.activeProjectName(), QStringLiteral("MeoArch OS"));
            QCOMPARE(store.projects().size(), 1);

            secondId = store.createProject(QStringLiteral("Science"));
            QVERIFY(!secondId.isEmpty());
            QCOMPARE(store.activeProjectId(), secondId);
            QCOMPARE(store.projects().size(), 2);
            QVERIFY(!store.renameProject(QStringLiteral("missing"), QStringLiteral("no")));
            QVERIFY(!store.renameProject(firstId, QStringLiteral("   ")));
            QVERIFY(store.renameProject(firstId, QStringLiteral("  MeoArch   Project "))); 
            QCOMPARE(store.projects().last().toMap().value(QStringLiteral("name")).toString(), QStringLiteral("MeoArch Project"));
            QVERIFY(!store.openProject(QStringLiteral("missing")));
            QVERIFY(store.openProject(firstId));
            QCOMPARE(store.activeProjectId(), firstId);
            QCOMPARE(store.projects().first().toMap().value(QStringLiteral("id")).toString(), firstId);
        }

        {
            ProjectStore restored;
            QCOMPARE(restored.projects().size(), 2);
            QCOMPARE(restored.activeProjectId(), firstId);
            QCOMPARE(restored.activeProjectName(), QStringLiteral("MeoArch Project"));
            restored.closeProject();
            QVERIFY(restored.activeProjectId().isEmpty());
        }

        {
            ProjectStore restored;
            QCOMPARE(restored.projects().size(), 2);
            QVERIFY(restored.activeProjectId().isEmpty());
        }
    }

    void ephemeralStoreDoesNotPersist()
    {
        QTemporaryDir config;
        QVERIFY(config.isValid());
        qputenv("XDG_CONFIG_HOME", config.path().toUtf8());
        QCoreApplication::setOrganizationName(QStringLiteral("MeoArchProjectStorePreviewTests"));
        QCoreApplication::setApplicationName(QStringLiteral("MeoAI"));

        {
            ProjectStore preview(false);
            QVERIFY(!preview.createProject(QStringLiteral("Preview only")).isEmpty());
            QCOMPARE(preview.projects().size(), 1);
        }
        ProjectStore restored;
        QCOMPARE(restored.projects().size(), 0);
    }
};

QTEST_MAIN(ProjectStoreTest)
#include "project-store-test.moc"

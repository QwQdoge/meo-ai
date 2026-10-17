#include "agentclient.h"
#include <QGuiApplication>
#include <QJSValue>
#include <QPointer>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickItem>
#include <QQuickWindow>
#include <QTemporaryDir>
#include <QTest>

namespace {
QQuickItem *item(QQuickItem *parent, const QString &name) {
    if (!parent) return nullptr;
    if (parent->objectName() == name) return parent;
    for (auto *child : parent->childItems())
        if (auto *found = item(child, name)) return found;
    return nullptr;
}

QList<QQuickItem *> items(QQuickItem *parent, const QString &name) {
    QList<QQuickItem *> found;
    if (!parent) return found;
    if (parent->objectName() == name) found.append(parent);
    for (auto *child : parent->childItems()) found.append(items(child, name));
    return found;
}
}

class UiLayoutTest : public QObject {
    Q_OBJECT
private slots:
    void responsiveLayoutAndPresentation() {
        QTemporaryDir config;
        QCoreApplication::setOrganizationName("MeoArchTests");
        qputenv("XDG_CONFIG_HOME", config.path().toUtf8());
        qputenv("MEO_AI_SERVICE_ENDPOINT", "http://127.0.0.1:9");
        AgentClient client;
        QQmlApplicationEngine engine;
        engine.addImportPath(QStringLiteral(MEOUI_IMPORT_PATH));
        engine.rootContext()->setContextProperty("agent", &client);
        // Main normally supplies UsageBackend. Keep the layout fixture small
        // while still exercising bindings in the complete Settings Center.
        engine.rootContext()->setContextProperty(
            "usage", QVariantMap{{QStringLiteral("status"), QStringLiteral("Fixture activity")},
                                 {QStringLiteral("busy"), false}});
        engine.rootContext()->setContextProperty("uiPreview", true);
        engine.load(QUrl("qrc:/meo/app/qml/App.qml"));
        QVERIFY(!engine.rootObjects().isEmpty());
        auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
        QVERIFY(window);
        window->resize(1560, 940);

        QPointer<QQuickItem> failureBanner;
        QTRY_VERIFY((failureBanner = item(window->contentItem(), "meoAiRequestFailure")) != nullptr);
        QVERIFY(failureBanner);
        QVERIFY(!failureBanner->isVisible());

        client.message("user", "Review this project");
        client.message("assistant", "Sample response");
        client.presentationEvent(QVariantMap{{"card", QVariantMap{
            {"card_id", "test"}, {"title", "Build"}, {"value", "Ready"}, {"kind", "status"}}}});
        client.responseMetaEvent(QVariantMap{
            {"model", "Fixture"},
            {"conversation_digest", QVariantMap{
                {"status", "completed"}, {"title", "Project Review"}, {"summary", "Reviewed the project."}}},
            {"citations", QVariantList{
                QVariantMap{{"title", "Fixture source"}, {"uri", "https://example.com"}}}}});

        QPointer<QQuickItem> title;
        QTRY_VERIFY((title = item(window->contentItem(), "meoAiConversationTitle")) != nullptr);
        QVERIFY(title);
        QTRY_COMPARE(title->property("text").toString(), QString("Project Review"));
        QCOMPARE(window->property("generatedConversationTitle").toString(), QString("Project Review"));

        QPointer<QQuickItem> card;
        QTRY_VERIFY((card = item(window->contentItem(), "meoAiPresentationCard")) != nullptr);
        QVERIFY(card);
        QCOMPARE(card->property("title").toString(), QString("Build"));
        QCOMPARE(card->property("cardValue").toString(), QString("Ready"));

        // presentation.card is an upsert contract: a later event with the same
        // card_id must update the existing visual card instead of appending a
        // duplicate. This keeps streaming status/metric cards stable in place.
        client.presentationEvent(QVariantMap{{"card", QVariantMap{
            {"card_id", "test"}, {"title", "Build"}, {"value", "Updated"}, {"kind", "status"}}}});
        QTRY_COMPARE(items(window->contentItem(), "meoAiPresentationCard").size(), 1);
        QTRY_COMPARE(card->property("cardValue").toString(), QString("Updated"));

        QPointer<QQuickItem> pane;
        QTRY_VERIFY((pane = item(window->contentItem(), "meoAiDetailsPane")) != nullptr);
        QVERIFY(pane);
        QCOMPARE(pane->property("metadata").value<QJSValue>().toVariant().toMap().value("citations").toList().size(), 1);

        // A later answer must not replace the sources shown for an earlier one.
        client.message("user", "Another question");
        client.message("assistant", "Another response");
        client.responseMetaEvent(QVariantMap{{"model", "Second fixture"}});
        QPointer<QQuickItem> responseDetails;
        QTRY_VERIFY((responseDetails = item(window->contentItem(), "meoAiResponseDetails-1")) != nullptr);
        QVERIFY(responseDetails);
        QVERIFY(QMetaObject::invokeMethod(responseDetails.data(), "clicked"));
        QTRY_VERIFY((pane = item(window->contentItem(), "meoAiDetailsPane")) != nullptr);
        QVERIFY(pane);
        QCOMPARE(pane->property("metadata").value<QJSValue>().toVariant().toMap().value("citations").toList().size(), 1);

        // Fill enough history to make the conversation genuinely scrollable,
        // then move away from the end. A streaming delta must update the last
        // message without yanking the reader back to the bottom.
        for (int i = 0; i < 18; ++i) {
            client.message("user", QString("Question %1 with enough text to occupy a visible row.").arg(i));
            client.message("assistant", QString("Answer %1 with enough text to occupy a visible row and make the history scroll.").arg(i));
        }
        QPointer<QQuickItem> history;
        QTRY_VERIFY((history = item(window->contentItem(), "meoAiHistory")) != nullptr);
        QVERIFY(history);
        QTRY_VERIFY(history->property("contentHeight").toReal() > history->height());
        QVERIFY(QMetaObject::invokeMethod(history.data(), "positionViewAtBeginning"));
        QTRY_VERIFY(history->property("contentY").toReal() <
                    history->property("contentHeight").toReal() - history->height() - 64);
        const qreal contentYBeforeDelta = history->property("contentY").toReal();
        client.delta(" streamed continuation");
        QTest::qWait(50);
        QVERIFY(qAbs(history->property("contentY").toReal() - contentYBeforeDelta) < 2.0);

        QPointer<QQuickItem> sidebar;
        QTRY_VERIFY((sidebar = item(window->contentItem(), "meoAiSidebar")) != nullptr);
        QVERIFY(sidebar);

        // Primary navigation is task-oriented. Work must be a distinct mode,
        // while model/memory/resource configuration is no longer top-level.
        QPointer<QQuickItem> workNavigation;
        QPointer<QQuickItem> chatNavigation;
        QPointer<QQuickItem> projectsNavigation;
        QPointer<QQuickItem> skillsNavigation;
        QTRY_VERIFY((workNavigation = item(window->contentItem(), "meoAiNav-work")) != nullptr);
        QTRY_VERIFY((chatNavigation = item(window->contentItem(), "meoAiNav-chat")) != nullptr);
        QTRY_VERIFY((projectsNavigation = item(window->contentItem(), "meoAiNav-projects")) != nullptr);
        QTRY_VERIFY((skillsNavigation = item(window->contentItem(), "meoAiNav-skills")) != nullptr);
        QVERIFY(workNavigation->isVisible());
        QVERIFY(projectsNavigation->isVisible());
        QVERIFY(skillsNavigation->isVisible());
        QVERIFY(item(window->contentItem(), "meoAiNav-models") == nullptr);
        QVERIFY(item(window->contentItem(), "meoAiNav-memory") == nullptr);
        QVERIFY(item(window->contentItem(), "meoAiNav-resources") == nullptr);

        QVERIFY(QMetaObject::invokeMethod(workNavigation.data(), "clicked"));
        QTRY_COMPARE(window->property("primaryMode").toString(), QString("work"));
        QPointer<QQuickItem> workLanding;
        QPointer<QQuickItem> workTarget;
        QTRY_VERIFY((workLanding = item(window->contentItem(), "meoAiModeLanding-work")) != nullptr);
        QTRY_VERIFY(workLanding->isVisible());
        QTRY_VERIFY((workTarget = item(window->contentItem(), "meoAiWorkTarget")) != nullptr);
        QTRY_VERIFY(workTarget->isVisible());
        QPointer<QQuickItem> composerShell;
        QTRY_VERIFY((composerShell = item(window->contentItem(), "meoAiComposerShell")) != nullptr);
        QVERIFY(!composerShell->isVisible());

        QVERIFY(QMetaObject::invokeMethod(chatNavigation.data(), "clicked"));
        QTRY_COMPARE(window->property("primaryMode").toString(), QString("chat"));
        QTRY_VERIFY(composerShell->isVisible());
        QVERIFY(QMetaObject::invokeMethod(window, "openInspector", Q_ARG(QVariant, 0)));
        QTRY_VERIFY(window->property("showDock").toBool());

        QTest::qWait(100);
        const qreal originalWidth = sidebar->width();
        const QPoint handle = sidebar->mapToScene(QPointF(originalWidth + 6, sidebar->height() / 2)).toPoint();
        QTest::mousePress(window, Qt::LeftButton, Qt::NoModifier, handle);
        QTest::mouseMove(window, handle + QPoint(45, 0), 100);
        QTest::mouseRelease(window, Qt::LeftButton, Qt::NoModifier, handle + QPoint(45, 0));
        QTRY_VERIFY(sidebar && sidebar->width() > originalWidth + 25);
        const qreal resizedWidth = sidebar->width();
        window->setProperty("sidebarHidden", true);
        QTRY_VERIFY(sidebar && !sidebar->isVisible());
        window->setProperty("sidebarHidden", false);
        QTRY_VERIFY(sidebar && sidebar->isVisible());
        QTRY_VERIFY(sidebar && qAbs(sidebar->width() - resizedWidth) < 2);

        // DetailsPane is a responsive component and may be recreated when its
        // dock/overlay host changes. Reacquire it before dereferencing it.
        QTRY_VERIFY((pane = item(window->contentItem(), "meoAiDetailsPane")) != nullptr);
        QVERIFY(pane);
        const qreal originalDetailsWidth = pane->width();
        const QPoint detailsHandle = pane->mapToScene(QPointF(-6, pane->height() / 2)).toPoint();
        QTest::mousePress(window, Qt::LeftButton, Qt::NoModifier, detailsHandle);
        QTest::mouseMove(window, detailsHandle - QPoint(45, 0), 100);
        QTest::mouseRelease(window, Qt::LeftButton, Qt::NoModifier, detailsHandle - QPoint(45, 0));
        QTRY_VERIFY(pane && pane->width() > originalDetailsWidth + 25);
        window->setProperty("inspectorOpen", false);
        QTRY_VERIFY(!window->property("showDock").toBool());
        QVERIFY(QMetaObject::invokeMethod(window, "openInspector", Q_ARG(QVariant, 0)));
        QTRY_VERIFY(window->property("showDock").toBool());

        // Sidebar tab 3 is the stable AI-settings contract. It must now open
        // the full multi-page Settings Center rather than the Activity view.
        QVERIFY(QMetaObject::invokeMethod(window, "openInspector", Q_ARG(QVariant, 3)));
        QCOMPARE(window->property("inspectorTab").toInt(), 3);
        // The dock Loader may have recreated DetailsPane. Select the visible
        // popup because the hidden host can still own another DetailsPane.
        QPointer<QObject> settingsCenter;
        QTRY_VERIFY(([&]() {
            for (auto *candidate : window->findChildren<QObject *>("meoAiSettingsCenter")) {
                if (candidate->property("visible").toBool()) {
                    settingsCenter = candidate;
                    return true;
                }
            }
            return false;
        })());
        QVERIFY(QMetaObject::invokeMethod(settingsCenter.data(), "close"));

        // Recreating DetailsPane with a persisted Settings tab is presentation
        // state only. New Chat/responsive host changes must not reopen the modal
        // without another explicit user tab change.
        window->setProperty("inspectorOpen", false);
        QTRY_VERIFY(!window->property("showDock").toBool());
        QCOMPARE(window->property("inspectorTab").toInt(), 3);
        window->setProperty("inspectorOpen", true);
        QTRY_VERIFY(window->property("showDock").toBool());
        QTest::qWait(100);
        for (auto *candidate : window->findChildren<QObject *>("meoAiSettingsCenter"))
            QVERIFY(!candidate->property("visible").toBool());

        // Activity exposes a stable support entry point. The test deliberately
        // does not click it, so CI never opens an external browser.
        QVERIFY(QMetaObject::invokeMethod(window, "openInspector", Q_ARG(QVariant, 4)));
        QCOMPARE(window->property("inspectorTab").toInt(), 4);
        QPointer<QQuickItem> reportIssue;
        QTRY_VERIFY((reportIssue = item(window->contentItem(), "meoAiReportIssue")) != nullptr);
        QVERIFY(reportIssue->isVisible());

        window->resize(960, 720);
        QTRY_VERIFY(!window->property("showDock").toBool());
        QTRY_VERIFY(sidebar && qAbs(sidebar->width() - 72) < 2);
        QVERIFY(QMetaObject::invokeMethod(window, "openInspector", Q_ARG(QVariant, 2)));
        QPointer<QObject> overlay = window->findChild<QObject *>("meoAiInspectorOverlay");
        QVERIFY(overlay);
        QTRY_VERIFY(overlay && overlay->property("visible").toBool());
        QCOMPARE(window->property("inspectorTab").toInt(), 2);
        QVERIFY(QMetaObject::invokeMethod(overlay.data(), "close"));
        window->resize(720, 640);
        QTRY_VERIFY(sidebar && !sidebar->isVisible());
        QPointer<QQuickItem> composer;
        QTRY_VERIFY((composer = item(window->contentItem(), "meoAiComposerShell")) != nullptr);
        QVERIFY(composer);
        QVERIFY(composer->width() > 400 && composer->width() < window->width());

        // Compact/mobile keeps the same hierarchy in a left Drawer. The Drawer
        // is interactive with a nonzero left-edge drag margin, so Qt Quick
        // provides the same edge-swipe gesture as the hamburger entry point.
        QPointer<QQuickItem> mobileMenuButton;
        QTRY_VERIFY((mobileMenuButton = item(window->contentItem(), "meoAiMobileMenuButton")) != nullptr);
        QVERIFY(mobileMenuButton->isVisible());
        QPointer<QObject> mobileDrawer = window->findChild<QObject *>("meoAiMobileNavigationDrawer");
        QTRY_VERIFY(mobileDrawer);
        QVERIFY(mobileDrawer->property("interactive").toBool());
        QVERIFY(mobileDrawer->property("dragMargin").toReal() > 0.0);
        QCOMPARE(mobileDrawer->property("edge").toInt(), static_cast<int>(Qt::LeftEdge));
        QVERIFY(QMetaObject::invokeMethod(mobileMenuButton.data(), "clicked"));
        QTRY_VERIFY(mobileDrawer->property("visible").toBool());
        QPointer<QObject> mobileWork = window->findChild<QObject *>("meoAiMobileNav-work");
        QTRY_VERIFY(mobileWork);
        QVERIFY(QMetaObject::invokeMethod(mobileWork.data(), "clicked"));
        QTRY_COMPARE(window->property("primaryMode").toString(), QString("work"));
        QTRY_VERIFY(!mobileDrawer->property("visible").toBool());
        QVERIFY(QMetaObject::invokeMethod(window, "selectPrimaryMode", Q_ARG(QVariant, "chat")));
        QTRY_COMPARE(window->property("primaryMode").toString(), QString("chat"));

        // Restored conversation metadata is presentation state, not response
        // metadata. It must update the title without populating Response details.
        client.resetChat();
        client.message("user", "Fallback title from history");
        client.message("assistant", "Restored response");
        client.conversationMetadata(QVariantMap{
            {"conversation_id", "meo:history"},
            {"title", "Restored Project Review"},
            {"summary", "Persisted conversation summary"},
            {"title_is_default", false},
        });
        QTRY_COMPARE(title->property("text").toString(), QString("Restored Project Review"));
        QCOMPARE(window->property("generatedConversationTitle").toString(),
                 QString("Restored Project Review"));
        QCOMPARE(window->property("inspectedMetadata").value<QJSValue>().toVariant().toMap().size(), 0);

        // A default persisted title should not hide the more useful first-user
        // fallback used by the native header.
        client.resetChat();
        client.message("user", "Fallback title from user");
        client.message("assistant", "Restored response");
        client.conversationMetadata(QVariantMap{
            {"conversation_id", "meo:default"},
            {"title", "New conversation"},
            {"title_is_default", true},
        });
        QTRY_COMPARE(title->property("text").toString(), QString("Fallback title from user"));
        QCOMPARE(window->property("generatedConversationTitle").toString(), QString());
    }
};

QTEST_MAIN(UiLayoutTest)
#include "ui-layout-test.moc"
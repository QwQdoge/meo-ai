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
        engine.load(QUrl("qrc:/meo/app/qml/Main.qml"));
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
        client.responseMetaEvent(QVariantMap{{"model", "Fixture"}, {"citations", QVariantList{
            QVariantMap{{"title", "Fixture source"}, {"uri", "https://example.com"}}}}});

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
    }
};

QTEST_MAIN(UiLayoutTest)
#include "ui-layout-test.moc"

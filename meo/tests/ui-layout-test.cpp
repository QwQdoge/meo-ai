#include "agentclient.h"
#include <QGuiApplication>
#include <QJSValue>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickItem>
#include <QQuickWindow>
#include <QTemporaryDir>
#include <QTest>

namespace {
QQuickItem *item(QQuickItem *parent, const QString &name) {
    if (parent->objectName() == name) return parent;
    for (auto *child : parent->childItems())
        if (auto *found = item(child, name)) return found;
    return nullptr;
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
        engine.rootContext()->setContextProperty("uiPreview", true);
        engine.load(QUrl("qrc:/meo/app/qml/Main.qml"));
        QVERIFY(!engine.rootObjects().isEmpty());
        auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
        QVERIFY(window);
        window->resize(1560, 940);
        client.message("user", "Review this project");
        client.message("assistant", "Sample response");
        client.presentationEvent(QVariantMap{{"card", QVariantMap{
            {"card_id", "test"}, {"title", "Build"}, {"value", "Ready"}, {"kind", "status"}}}});
        client.responseMetaEvent(QVariantMap{{"model", "Fixture"}, {"citations", QVariantList{
            QVariantMap{{"title", "Fixture source"}, {"uri", "https://example.com"}}}}});
        QTRY_VERIFY(item(window->contentItem(), "meoAiPresentationCard"));
        auto *card = item(window->contentItem(), "meoAiPresentationCard");
        QCOMPARE(card->property("title").toString(), QString("Build"));
        QCOMPARE(card->property("cardValue").toString(), QString("Ready"));
        auto *pane = item(window->contentItem(), "meoAiDetailsPane");
        QVERIFY(pane);
        QCOMPARE(pane->property("metadata").value<QJSValue>().toVariant().toMap().value("citations").toList().size(), 1);
        // A later answer must not replace the sources shown for an earlier one.
        client.message("user", "Another question");
        client.message("assistant", "Another response");
        client.responseMetaEvent(QVariantMap{{"model", "Second fixture"}});
        QTRY_VERIFY(item(window->contentItem(), "meoAiResponseDetails-1"));
        QVERIFY(QMetaObject::invokeMethod(item(window->contentItem(), "meoAiResponseDetails-1"), "clicked"));
        QCOMPARE(pane->property("metadata").value<QJSValue>().toVariant().toMap().value("citations").toList().size(), 1);

        auto *sidebar = item(window->contentItem(), "meoAiSidebar");
        QVERIFY(sidebar);
        QTest::qWait(100);
        const qreal originalWidth = sidebar->width();
        const QPoint handle = sidebar->mapToScene(QPointF(originalWidth + 6, sidebar->height() / 2)).toPoint();
        QTest::mousePress(window, Qt::LeftButton, Qt::NoModifier, handle);
        QTest::mouseMove(window, handle + QPoint(45, 0), 100);
        QTest::mouseRelease(window, Qt::LeftButton, Qt::NoModifier, handle + QPoint(45, 0));
        QTRY_VERIFY(sidebar->width() > originalWidth + 25);
        const qreal resizedWidth = sidebar->width();
        window->setProperty("sidebarHidden", true);
        QTRY_VERIFY(!sidebar->isVisible());
        window->setProperty("sidebarHidden", false);
        QTRY_VERIFY(sidebar->isVisible());
        QTRY_VERIFY(qAbs(sidebar->width() - resizedWidth) < 2);
        const qreal originalDetailsWidth = pane->width();
        const QPoint detailsHandle = pane->mapToScene(QPointF(-6, pane->height() / 2)).toPoint();
        QTest::mousePress(window, Qt::LeftButton, Qt::NoModifier, detailsHandle);
        QTest::mouseMove(window, detailsHandle - QPoint(45, 0), 100);
        QTest::mouseRelease(window, Qt::LeftButton, Qt::NoModifier, detailsHandle - QPoint(45, 0));
        QTRY_VERIFY(pane->width() > originalDetailsWidth + 25);
        window->setProperty("inspectorOpen", false);
        QTRY_VERIFY(!window->property("showDock").toBool());
        QVERIFY(QMetaObject::invokeMethod(window, "openInspector", Q_ARG(QVariant, 0)));
        QTRY_VERIFY(window->property("showDock").toBool());

        window->resize(960, 720);
        QTRY_VERIFY(!window->property("showDock").toBool());
        QTRY_VERIFY(qAbs(sidebar->width() - 72) < 2);
        QVERIFY(QMetaObject::invokeMethod(window, "openInspector", Q_ARG(QVariant, 2)));
        auto *overlay = window->findChild<QObject *>("meoAiInspectorOverlay");
        QVERIFY(overlay);
        QTRY_VERIFY(overlay->property("visible").toBool());
        QCOMPARE(window->property("inspectorTab").toInt(), 2);
        QVERIFY(QMetaObject::invokeMethod(overlay, "close"));
        window->resize(720, 640);
        QTRY_VERIFY(!sidebar->isVisible());
        auto *composer = item(window->contentItem(), "meoAiComposerShell");
        QVERIFY(composer);
        QVERIFY(composer->width() > 400 && composer->width() < window->width());
    }
};

QTEST_MAIN(UiLayoutTest)
#include "ui-layout-test.moc"

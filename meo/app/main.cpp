#include "agentclient.h"
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QTimer>
#include <QQuickWindow>
int main(int argc, char **argv) {
    QGuiApplication app(argc, argv);
    app.setOrganizationName("MeoArch"); app.setApplicationName("MeoAI");
    QQmlApplicationEngine engine;
    engine.addImportPath(QStringLiteral(MEOUI_IMPORT_PATH));
    AgentClient client;
    engine.rootContext()->setContextProperty("agent", &client);
    engine.load(QUrl("qrc:/meo/app/qml/Main.qml"));
    if (engine.rootObjects().isEmpty()) return 1;
    const int screenshot = app.arguments().indexOf("--screenshot");
    if (screenshot >= 0 && screenshot + 1 < app.arguments().size()) {
        const QString path = app.arguments().at(screenshot + 1);
        QTimer::singleShot(1000, &app, [&] {
            auto window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
            app.exit(window && window->grabWindow().save(path) ? 0 : 2);
        });
        return app.exec();
    }
    if (app.arguments().contains("--smoke")) QTimer::singleShot(500, &app, &QCoreApplication::quit);
    return app.exec();
}

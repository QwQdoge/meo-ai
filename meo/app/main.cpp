#include "agentclient.h"
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QTimer>
#include <QQuickWindow>
#include <cstdio>
int main(int argc, char **argv) {
    QGuiApplication app(argc, argv);
    app.setOrganizationName("MeoArch"); app.setApplicationName("MeoAI");

    // Phase B is the default native path. Preserve the Phase A API only as an
    // explicit compatibility fallback: setting MEO_AI_ENDPOINT keeps the
    // legacy client, while MEO_AI_SERVICE_ENDPOINT always takes precedence.
    // Never fall back after a request has been submitted, because replaying a
    // message across transports could duplicate tool or system side effects.
    if (qEnvironmentVariableIsEmpty("MEO_AI_SERVICE_ENDPOINT") &&
        qEnvironmentVariableIsEmpty("MEO_AI_ENDPOINT")) {
        qputenv("MEO_AI_SERVICE_ENDPOINT", "http://127.0.0.1:8765");
    }

    AgentClient client;
    if (app.arguments().contains("--print-transport")) {
        std::puts(client.serviceMode() ? "service" : "legacy");
        return 0;
    }

    QQmlApplicationEngine engine;
    engine.addImportPath(QStringLiteral(MEOUI_IMPORT_PATH));
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

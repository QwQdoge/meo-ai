#include "agentclient.h"
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickWindow>
#include <QTimer>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <cstdio>

// Opt-in acceptance against a real AgentService, using the production QML UI.
// Run with a dedicated XDG_CONFIG_HOME to preserve the user's conversation.
int main(int argc, char **argv) {
    QGuiApplication app(argc, argv);
    app.setOrganizationName("MeoArch");
    app.setApplicationName("MeoAI");
    if (qEnvironmentVariableIsEmpty("MEO_AI_SERVICE_ENDPOINT")) {
        std::fputs("Set MEO_AI_SERVICE_ENDPOINT explicitly for live acceptance.\n", stderr);
        return 2;
    }
    const auto args = app.arguments();
    const auto value = [&](const QString &key) {
        const int index = args.indexOf(key);
        return index >= 0 && index + 1 < args.size() ? args.at(index + 1) : QString();
    };
    const QString prompt = value("--prompt");
    const QString screenshot = value("--screenshot");
    const bool historyOnly = args.contains("--history");
    const bool stop = args.contains("--cancel-after-delta");
    if (prompt.isEmpty() && !historyOnly) return 2;
    AgentClient client;
    QQmlApplicationEngine engine;
    engine.addImportPath(QStringLiteral(MEOUI_IMPORT_PATH));
    engine.rootContext()->setContextProperty("agent", &client);
    int messages = 0, deltas = 0;
    bool submitted = false, cancelled = false, finishing = false;
    QString answer;
    QJsonArray toolEvents;
    QObject::connect(&client, &AgentClient::toolEvent, &app, [&](const QVariantMap &event) {
        toolEvents.append(QJsonObject::fromVariantMap(event));
    });
    QObject::connect(&client, &AgentClient::message, &app,
                     [&](const QString &, const QString &) { ++messages; });
    QObject::connect(&client, &AgentClient::delta, &app, [&](const QString &text) {
        ++deltas;
        answer += text;
        if (stop && !cancelled) {
            cancelled = true;
            QTimer::singleShot(100, &client, &AgentClient::cancel);
        }
    });
    engine.load(QUrl("qrc:/meo/app/qml/Main.qml"));
    if (engine.rootObjects().isEmpty()) return 2;
    auto finish = [&] {
        if (finishing) return;
        finishing = true;
        QTimer::singleShot(500, &app, [&] {
            auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
            const bool captured = screenshot.isEmpty() || (window && window->grabWindow().save(screenshot));
            const bool passed = client.agentState().value("ready").toBool() && captured &&
                (historyOnly ? messages >= 2 : (deltas > 0 && client.status() == (stop ? "Stopped" : "Ready"))) &&
                (!args.contains("--require-tool") || !toolEvents.isEmpty());
            const auto report = QJsonDocument(QJsonObject{
                {"tool_events", toolEvents}, {"passed", passed}, {"status", client.status()}, {"messages", messages},
                {"deltas", deltas}, {"cancel_requested", cancelled}, {"answer", answer},
                {"screenshot_saved", captured}, {"history_only", historyOnly}}).toJson();
            std::fwrite(report.constData(), 1, report.size(), stdout);
            app.exit(passed ? 0 : 1);
        });
    };
    QTimer poll;
    poll.setInterval(100);
    QObject::connect(&poll, &QTimer::timeout, &app, [&] {
        if (client.busy() || client.actionBusy() || client.metadataBusy()) return;
        if (historyOnly) {
            if (client.agentState().value("ready").toBool()) finish();
        } else if (!submitted && client.agentState().value("ready").toBool()) {
            submitted = true;
            QMetaObject::invokeMethod(engine.rootObjects().first(), "submit", Q_ARG(QVariant, prompt));
        } else if (submitted) {
            finish();
        }
    });
    poll.start();
    QTimer::singleShot(180000, &app, [&] { client.cancel(); app.exit(3); });
    return app.exec();
}

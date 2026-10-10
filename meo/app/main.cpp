#include "nativeagentclient.h"
#include "usagebackend.h"
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QTimer>
#include <QQuickWindow>
#include <QSize>
#include <QVariantMap>
#include <cstdio>

namespace {
QSize requestedWindowSize(const QStringList &arguments)
{
    const int index = arguments.indexOf(QStringLiteral("--size"));
    if (index < 0 || index + 1 >= arguments.size())
        return {};

    const QStringList parts = arguments.at(index + 1).toLower().split(QLatin1Char('x'));
    if (parts.size() != 2)
        return {};

    bool widthOk = false;
    bool heightOk = false;
    const int width = parts.at(0).toInt(&widthOk);
    const int height = parts.at(1).toInt(&heightOk);
    if (!widthOk || !heightOk || width < 1 || height < 1)
        return {};
    return QSize(width, height);
}

void seedUiDemo(AgentClient &client)
{
    client.message(QStringLiteral("user"),
                   QStringLiteral("Check the current MeoArch project and show only what needs attention."));
    client.message(QStringLiteral("assistant"),
                   QStringLiteral("Here is a sample project review.\n\n### What needs attention\n\n1. **Router policy** — system actions require an explicit decision before execution.\n2. **Build warnings** — review nonblocking diagnostics after a successful build.\n3. **Documentation** — add usage examples where the interface has changed.\n\nThe cards below illustrate how structured results sit alongside a response."));
    client.toolEvent(QVariantMap{{"type", "tool.completed"}, {"request_id", "preview"},
                               {"tool_name", "Read project documents"},
                               {"display_text", "Sample activity · no files were read"}});
    client.responseMetaEvent(QVariantMap{
        {"request_id", "preview"}, {"provider", "Offline preview"}, {"model", "Sample AI"},
        {"usage", QVariantMap{{"input_tokens", 1245}, {"output_tokens", 2341}, {"total_tokens", 3586}}},
        {"timing", QVariantMap{{"total_ms", 12400}, {"first_token_ms", 310}}},
        {"activity", QVariantMap{{"tools", true}}},
        {"citations", QVariantList{QVariantMap{{"title", "Meo AI repository · sample source"},
                                               {"uri", "https://github.com/QwQdoge/meo-ai"}}}}});

    const auto present = [&client](const QString &id,
                                   const QString &kind,
                                   const QString &title,
                                   const QString &subtitle,
                                   const QString &value,
                                   const QString &detail) {
        QVariantMap card;
        card.insert(QStringLiteral("card_id"), id);
        card.insert(QStringLiteral("kind"), kind);
        card.insert(QStringLiteral("title"), title);
        card.insert(QStringLiteral("subtitle"), subtitle);
        card.insert(QStringLiteral("value"), value);
        card.insert(QStringLiteral("detail"), detail);
        QVariantMap event;
        event.insert(QStringLiteral("card"), card);
        client.presentationEvent(event);
    };

    present(QStringLiteral("demo:build"),
            QStringLiteral("status"),
            QStringLiteral("Preview validation"),
            QStringLiteral("Native + protocol"),
            QStringLiteral("Passing"),
            QStringLiteral("Latest checks completed without blocking errors."));
    present(QStringLiteral("demo:memory"),
            QStringLiteral("metric"),
            QStringLiteral("Memory"),
            QStringLiteral("Current session"),
            QStringLiteral("7.4 / 32 GB"),
            QStringLiteral("Normal for the current development workload."));
    present(QStringLiteral("demo:workspace"),
            QStringLiteral("system"),
            QStringLiteral("Workspace"),
            QStringLiteral("Meo AI"),
            QStringLiteral("Ready"),
            QStringLiteral("System actions still require Router policy and confirmation."));
}
}

int main(int argc, char **argv) {
    QGuiApplication app(argc, argv);
    app.setOrganizationName("MeoArch"); app.setApplicationName("MeoAI");

    if (qEnvironmentVariableIsEmpty("MEO_AI_SERVICE_ENDPOINT") &&
        qEnvironmentVariableIsEmpty("MEO_AI_ENDPOINT")) {
        qputenv("MEO_AI_SERVICE_ENDPOINT", "http://127.0.0.1:8765");
    }

    NativeAgentClient client;
    if (app.arguments().contains("--print-transport")) {
        std::puts(client.serviceMode() ? "service" : "legacy");
        return 0;
    }

    UsageBackend usageBackend;
    QQmlApplicationEngine engine;
    engine.addImportPath(QStringLiteral(MEOUI_IMPORT_PATH));
    engine.rootContext()->setContextProperty("agent", &client);
    engine.rootContext()->setContextProperty("usage", &usageBackend);
    engine.rootContext()->setContextProperty("uiPreview", app.arguments().contains("--ui-demo"));
    engine.load(QUrl("qrc:/meo/app/qml/Main.qml"));
    if (engine.rootObjects().isEmpty()) return 1;

    auto window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
    const QSize requestedSize = requestedWindowSize(app.arguments());
    if (window && requestedSize.isValid())
        window->resize(requestedSize);

    if (app.arguments().contains("--ui-demo"))
        seedUiDemo(client);

    const int screenshot = app.arguments().indexOf("--screenshot");
    if (screenshot >= 0 && screenshot + 1 < app.arguments().size()) {
        const QString path = app.arguments().at(screenshot + 1);
        QTimer::singleShot(1000, &app, [&, path] {
            app.exit(window && window->grabWindow().save(path) ? 0 : 2);
        });
        return app.exec();
    }
    if (app.arguments().contains("--smoke")) QTimer::singleShot(500, &app, &QCoreApplication::quit);
    return app.exec();
}

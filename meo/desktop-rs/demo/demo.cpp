// Offline host for the desktop QML: loads ../qml/Main.qml against a canned `core.view` JSON file,
// so the UI can be built, rendered and screenshotted without the Rust core, the network or an account.
//   meo-ai-demo --view views/chat.json [--shot out.png] [--size 1180x780]
// Dark mode: put {"prefs": {"appearance.theme": "dark"}} in the view file.
// Actions the UI sends are printed to stdout, one JSON object per line.
#include <QCommandLineParser>
#include <QFile>
#include <QGuiApplication>
#include <QElapsedTimer>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QQmlApplicationEngine>
#include <QQuickWindow>
#include <QTimer>
#include <algorithm>
#include <QTextStream>

class DemoCore : public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariant view READ view NOTIFY viewChanged)
public:
    QVariant view() const { return m_view; }
    void load(const QString &path) {
        QFile f(path);
        if (!f.open(QIODevice::ReadOnly)) { qCritical() << "cannot read" << path; return; }
        m_json = QJsonDocument::fromJson(f.readAll()).object();
        m_view = m_json.toVariantMap();
        emit viewChanged();
    }
    // Streaming benchmark: appends a word to the last assistant message, like one streamed token.
    void appendToken() {
        QJsonObject page = m_json["page"].toObject();
        QJsonArray messages = page["messages"].toArray();
        if (messages.isEmpty()) return;
        QJsonObject last = messages.last().toObject();
        last["text"] = last["text"].toString() + " token";
        last["streaming"] = true;
        QJsonArray blocks = last["blocks"].toArray();
        if (!blocks.isEmpty()) {
            QJsonObject b = blocks.last().toObject();
            b["text"] = b["text"].toString() + " token";
            blocks[blocks.size() - 1] = b;
            last["blocks"] = blocks;
        }
        messages[messages.size() - 1] = last;
        page["messages"] = messages;
        m_json["page"] = page;
        QElapsedTimer t;
        t.start();
        QJsonObject sent = m_json;
        if (qEnvironmentVariableIsSet("MEO_BENCH_DELTA")) {
            // What the desktop host sends (message_delta.rs): unchanged stored messages as placeholders.
            QJsonObject sentPage = page;
            QJsonArray stubs;
            for (int i = 0; i < messages.size(); ++i) {
                QJsonObject m = messages[i].toObject();
                if (i < messages.size() - 1 && !m["id"].toString().isEmpty())
                    stubs.append(QJsonObject{{"id", m["id"]}, {"same", true}});
                else
                    stubs.append(m);
            }
            sentPage["messages"] = stubs;
            sent["page"] = sentPage;
        }
        m_view = sent.toVariantMap();   // the real host converts the whole view too
        const double convert = t.nsecsElapsed() / 1e6;
        t.restart();
        emit viewChanged();               // runs the QML bindings synchronously
        const double bindings = t.nsecsElapsed() / 1e6;
        if (qEnvironmentVariableIsSet("MEO_BENCH_VERBOSE"))
            QTextStream(stdout) << "  convert " << convert << " ms, bindings " << bindings << " ms" << Qt::endl;
    }
    Q_INVOKABLE void dispatch(const QString &action) { QTextStream(stdout) << action << Qt::endl; }
    Q_INVOKABLE void activate() { emit activateRequested(); }
signals:
    void viewChanged();
    void activateRequested();
private:
    QVariant m_view;
    QJsonObject m_json;
};

int main(int argc, char **argv) {
    QGuiApplication app(argc, argv);
    QCommandLineParser p;
    p.addHelpOption();
    QCommandLineOption view("view", "Canned view JSON.", "file");
    QCommandLineOption shot("shot", "Save a PNG and exit.", "png");
    QCommandLineOption size("size", "Window size.", "WxH", "1180x780");
    QCommandLineOption bench("bench", "Stream N tokens into the last message and report the cost.", "N");
    QCommandLineOption qml("qml", "Directory with Main.qml.", "dir", QStringLiteral(MEO_DEMO_QML_DIR));
    p.addOptions({view, shot, size, qml, bench});
    p.process(app);

    DemoCore core;
    core.load(p.value(view));
    QQmlApplicationEngine engine;
    engine.addImportPath(p.value(qml));
    engine.addImportPath(QStringLiteral(MEOUI_IMPORT_PATH));
    engine.setInitialProperties({{"core", QVariant::fromValue(&core)}});
    engine.load(QUrl::fromLocalFile(p.value(qml) + "/Main.qml"));
    if (engine.rootObjects().isEmpty()) return 2;
    auto *win = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
    const auto wh = p.value(size).split('x');
    if (wh.size() == 2) win->resize(wh[0].toInt(), wh[1].toInt());
    if (p.isSet(bench)) {
        const int n = p.value(bench).toInt();
        QElapsedTimer clock;
        QList<double> samples;
        int done = 0;
        auto *tick = new QTimer(&app);
        tick->setInterval(120);
        // Wait for the first frame, then: mutate, and time until the next frame has been swapped.
        QObject::connect(win, &QQuickWindow::frameSwapped, &app, [&] {
            if (clock.isValid()) { samples << clock.nsecsElapsed() / 1e6; clock.invalidate(); }
        });
        QObject::connect(tick, &QTimer::timeout, &app, [&] {
            if (done++ >= n) {
                std::sort(samples.begin(), samples.end());
                double sum = 0; for (double x : samples) sum += x;
                QTextStream(stdout) << "bench: " << samples.size() << " updates, mean " << sum / qMax(1, int(samples.size()))
                                    << " ms, median " << (samples.isEmpty() ? 0 : samples[samples.size() / 2])
                                    << " ms, worst " << (samples.isEmpty() ? 0 : samples.last()) << " ms" << Qt::endl;
                QGuiApplication::exit(0);
                return;
            }
            clock.start();
            core.appendToken();
        });
        QTimer::singleShot(1500, &app, [tick] { tick->start(); });
    }
    if (p.isSet(shot)) {
        QTimer::singleShot(1500, [&] {
            const bool ok = win->grabWindow().save(p.value(shot));
            QGuiApplication::exit(ok ? 0 : 3);
        });
    }
    return app.exec();
}
#include "demo.moc"

// Offline host for the desktop QML: loads ../qml/Main.qml against a canned `core.view` JSON file,
// so the UI can be built, rendered and screenshotted without the Rust core, the network or an account.
//   meo-ai-demo --view views/chat.json [--shot out.png] [--size 1180x780]
// Dark mode: put {"prefs": {"appearance.theme": "dark"}} in the view file.
// Actions the UI sends are printed to stdout, one JSON object per line.
#include <QCommandLineParser>
#include <QFile>
#include <QGuiApplication>
#include <QJsonDocument>
#include <QQmlApplicationEngine>
#include <QQuickWindow>
#include <QTimer>
#include <QTextStream>

class DemoCore : public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariant view READ view NOTIFY viewChanged)
public:
    QVariant view() const { return m_view; }
    void load(const QString &path) {
        QFile f(path);
        if (!f.open(QIODevice::ReadOnly)) { qCritical() << "cannot read" << path; return; }
        m_view = QJsonDocument::fromJson(f.readAll()).toVariant();
        emit viewChanged();
    }
    Q_INVOKABLE void dispatch(const QString &action) { QTextStream(stdout) << action << Qt::endl; }
    Q_INVOKABLE void activate() { emit activateRequested(); }
signals:
    void viewChanged();
    void activateRequested();
private:
    QVariant m_view;
};

int main(int argc, char **argv) {
    QGuiApplication app(argc, argv);
    QCommandLineParser p;
    p.addHelpOption();
    QCommandLineOption view("view", "Canned view JSON.", "file");
    QCommandLineOption shot("shot", "Save a PNG and exit.", "png");
    QCommandLineOption size("size", "Window size.", "WxH", "1180x780");
    QCommandLineOption qml("qml", "Directory with Main.qml.", "dir", QStringLiteral(MEO_DEMO_QML_DIR));
    p.addOptions({view, shot, size, qml});
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
    if (p.isSet(shot)) {
        QTimer::singleShot(1500, [&] {
            const bool ok = win->grabWindow().save(p.value(shot));
            QGuiApplication::exit(ok ? 0 : 3);
        });
    }
    return app.exec();
}
#include "demo.moc"

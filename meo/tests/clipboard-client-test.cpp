#include "agentclient.h"

#include <QClipboard>
#include <QFile>
#include <QGuiApplication>
#include <QMimeData>
#include <QSettings>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
#include <QTest>

class ClipboardClientTest : public QObject {
    Q_OBJECT
private:
    static QByteArray readRequest(QTcpSocket *socket) {
        QByteArray request;
        for (int i = 0; i < 100 && !request.contains("\r\n\r\n"); ++i) {
            if (!socket->bytesAvailable()) socket->waitForReadyRead(30);
            request += socket->readAll();
        }
        return request;
    }

    static void replyJson(QTcpSocket *socket, int status, const QByteArray &body) {
        const QByteArray statusText = status == 201 ? "201 Created" : "200 OK";
        socket->write("HTTP/1.1 " + statusText
                      + "\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                      + QByteArray::number(body.size()) + "\r\n\r\n" + body);
        socket->flush();
        socket->disconnectFromHost();
    }

    static void writeFile(const QString &path, const QByteArray &content) {
        QFile file(path);
        QVERIFY(file.open(QIODevice::WriteOnly));
        QCOMPARE(file.write(content), content.size());
    }

private slots:
    void initTestCase() {
        QCoreApplication::setOrganizationName("MeoArchClipboardClientTest");
        QCoreApplication::setApplicationName("MeoAIClipboardClientTest");
    }

    void cleanup() {
        QGuiApplication::clipboard()->clear();
        QSettings().clear();
        qunsetenv("MEO_AI_SERVICE_ENDPOINT");
    }

    void localClipboardFilesAreQueuedButWebUrlsAreIgnored() {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());
        QSettings().clear();

        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString alpha = directory.filePath("alpha.txt");
        const QString beta = directory.filePath("beta.txt");
        writeFile(alpha, "alpha");
        writeFile(beta, "beta");

        auto *mime = new QMimeData;
        mime->setUrls({
            QUrl::fromLocalFile(alpha),
            QUrl(QStringLiteral("https://example.com/not-downloaded.txt")),
            QUrl::fromLocalFile(beta),
        });
        QGuiApplication::clipboard()->setMimeData(mime);

        AgentClient client;
        QCOMPARE(client.addClipboardResources(), 2);

        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *create = server.nextPendingConnection();
        QVERIFY(readRequest(create).startsWith("POST /v1/conversations "));
        replyJson(create, 201, "{\"conversation_id\":\"meo:clipboard\"}");
        create->deleteLater();

        // The first local file is now being reserved/uploaded. The second is
        // already queued inside AgentClient; the HTTPS URL did not create a
        // third queued item or trigger any network download.
        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *reserve = server.nextPendingConnection();
        const QByteArray reserveRequest = readRequest(reserve);
        QVERIFY(reserveRequest.contains("POST /v1/conversations/meo:clipboard/resources"));
        QVERIFY(reserveRequest.contains("alpha.txt"));
        reserve->disconnectFromHost();
        reserve->deleteLater();
    }

    void remoteClipboardUrlAloneIsNotFetched() {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());

        auto *mime = new QMimeData;
        mime->setUrls({QUrl(QStringLiteral("https://example.com/private-link"))});
        QGuiApplication::clipboard()->setMimeData(mime);

        AgentClient client;
        QCOMPARE(client.addClipboardResources(), 0);
        QVERIFY(client.status().contains(QStringLiteral("local files or an image")));
        QTest::qWait(40);
        QVERIFY(!server.hasPendingConnections());
    }
};

int main(int argc, char **argv) {
    QGuiApplication app(argc, argv);
    ClipboardClientTest test;
    return QTest::qExec(&test, argc, argv);
}

#include "clipboard-client-test.moc"

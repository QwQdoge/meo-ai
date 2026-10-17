#include "agentclient.h"

#include <QFile>
#include <QSettings>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
#include <QTest>

class ConversationExportTest : public QObject {
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

    static void replyJson(QTcpSocket *socket, const QByteArray &body) {
        socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                      + QByteArray::number(body.size()) + "\r\n\r\n" + body);
        socket->flush();
        socket->disconnectFromHost();
    }

private slots:
    void initTestCase() {
        QCoreApplication::setOrganizationName("MeoArchConversationExportTest");
        QCoreApplication::setApplicationName("MeoAIConversationExportTest");
    }

    void cleanup() {
        QSettings().clear();
        qunsetenv("MEO_AI_SERVICE_ENDPOINT");
    }

    void exportsOnlyVisibleConversationMessages() {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());

        AgentClient client;
        client.refreshConversations();
        QTRY_VERIFY(server.hasPendingConnections());
        auto catalogSocket = server.nextPendingConnection();
        QVERIFY(readRequest(catalogSocket).contains("GET /v1/conversations "));
        replyJson(catalogSocket,
                  "{\"conversations\":[{\"id\":\"meo:export\",\"title\":\"Project notes\"}]}");
        QTRY_COMPARE(client.conversations().size(), 1);
        catalogSocket->deleteLater();

        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString target = directory.filePath("chat.md");
        client.exportConversation("meo:export", QUrl::fromLocalFile(target));

        QTRY_VERIFY(server.hasPendingConnections());
        auto historySocket = server.nextPendingConnection();
        QVERIFY(readRequest(historySocket).contains("GET /v1/conversations/meo:export/messages"));
        replyJson(historySocket,
                  "{\"conversation_id\":\"meo:export\",\"messages\":["
                  "{\"role\":\"user\",\"text\":\"Question with **Markdown**\"},"
                  "{\"role\":\"tool\",\"text\":\"internal secret\"},"
                  "{\"role\":\"assistant\",\"text\":\"Answer text\"}]}");
        historySocket->deleteLater();

        QTRY_COMPARE(client.status(), QString("Conversation exported."));
        QFile file(target);
        QVERIFY(file.open(QIODevice::ReadOnly));
        const QString markdown = QString::fromUtf8(file.readAll());
        QVERIFY(markdown.startsWith(QStringLiteral("# Project notes\n")));
        QVERIFY(markdown.contains(QStringLiteral("## You\n\nQuestion with **Markdown**")));
        QVERIFY(markdown.contains(QStringLiteral("## Meo AI\n\nAnswer text")));
        QVERIFY(!markdown.contains(QStringLiteral("internal secret")));
    }

    void rejectsRemoteExportTargetWithoutNetworkRequest() {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());

        AgentClient client;
        client.refreshConversations();
        QTRY_VERIFY(server.hasPendingConnections());
        auto catalogSocket = server.nextPendingConnection();
        readRequest(catalogSocket);
        replyJson(catalogSocket,
                  "{\"conversations\":[{\"id\":\"meo:export\",\"title\":\"Project notes\"}]}");
        QTRY_COMPARE(client.conversations().size(), 1);
        catalogSocket->deleteLater();

        client.exportConversation("meo:export", QUrl(QStringLiteral("https://example.com/chat.md")));
        QCOMPARE(client.status(), QString("Choose a local file for the export."));
        QTest::qWait(40);
        QVERIFY(!server.hasPendingConnections());
    }
};

QTEST_GUILESS_MAIN(ConversationExportTest)
#include "conversation-export-test.moc"

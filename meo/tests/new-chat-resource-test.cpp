#include "nativeagentclient.h"

#include <QJsonDocument>
#include <QJsonObject>
#include <QSettings>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTest>

class NewChatResourceTest : public QObject {
    Q_OBJECT

private:
    static QByteArray readRequest(QTcpSocket *socket) {
        QByteArray request;
        for (int i = 0; i < 100 && !request.contains("\r\n\r\n"); ++i) {
            if (!socket->bytesAvailable()) socket->waitForReadyRead(30);
            request += socket->readAll();
        }
        const int headerEnd = request.indexOf("\r\n\r\n");
        if (headerEnd < 0) return request;
        const QByteArray headers = request.left(headerEnd);
        const int marker = headers.toLower().indexOf("content-length:");
        if (marker < 0) return request;
        const int valueStart = marker + QByteArray("content-length:").size();
        const int valueEnd = headers.indexOf("\r\n", valueStart);
        const int length = headers.mid(valueStart, valueEnd - valueStart).trimmed().toInt();
        while (request.size() - headerEnd - 4 < length) {
            if (!socket->waitForReadyRead(30)) break;
            request += socket->readAll();
        }
        return request;
    }

    static void replyJson(QTcpSocket *socket, int status, const QByteArray &body) {
        const QByteArray statusText = status == 200 ? QByteArrayLiteral("200 OK")
            : status == 201 ? QByteArrayLiteral("201 Created")
            : status == 404 ? QByteArrayLiteral("404 Not Found")
            : status == 503 ? QByteArrayLiteral("503 Service Unavailable")
                            : QByteArray::number(status) + " Error";
        socket->write("HTTP/1.1 " + statusText
                      + "\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                      + QByteArray::number(body.size()) + "\r\n\r\n" + body);
        socket->flush();
        socket->disconnectFromHost();
    }

    static void attachLongText(
        NativeAgentClient &client,
        QTcpServer &server,
        const QByteArray &conversationId,
        const QByteArray &resourceId
    ) {
        client.addLongTextResource(QStringLiteral("old.txt"), QStringLiteral("old context"));

        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *create = server.nextPendingConnection();
        const QByteArray createRequest = readRequest(create);
        QVERIFY(createRequest.startsWith("POST /v1/conversations "));
        replyJson(create, 201, "{\"conversation_id\":\"" + conversationId + "\"}");
        create->deleteLater();

        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *resource = server.nextPendingConnection();
        const QByteArray resourceRequest = readRequest(resource);
        QVERIFY(resourceRequest.contains("POST /v1/conversations/" + conversationId + "/resources/text"));
        replyJson(
            resource,
            201,
            "{\"conversation_id\":\"" + conversationId
                + "\",\"resource\":{\"resource_id\":\"" + resourceId
                + "\",\"kind\":\"long_text\",\"name\":\"old.txt\","
                  "\"mime_type\":\"text/plain; charset=utf-8\",\"size_bytes\":11,"
                  "\"sha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\","
                  "\"state\":\"ready\"}}");
        resource->deleteLater();
        QTRY_COMPARE(client.pendingResources().size(), 1);
        QTRY_VERIFY(!client.actionBusy());
    }

    static void expectNewChatAfterDeleteResult(int deleteStatus) {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());
        QSettings().clear();

        NativeAgentClient client;
        const QByteArray oldConversation = "meo:old-resource-chat";
        const QByteArray resourceId = "resource:55555555555555555555555555555555";
        attachLongText(client, server, oldConversation, resourceId);

        client.newChat();
        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *remove = server.nextPendingConnection();
        const QByteArray deleteRequest = readRequest(remove);
        QVERIFY(deleteRequest.contains(
            "DELETE /v1/conversations/" + oldConversation + "/resources/" + resourceId));

        // The new conversation must not be created while an old scoped resource
        // is still being deleted/abandoned.
        QTest::qWait(20);
        QVERIFY(!server.hasPendingConnections());

        replyJson(remove, deleteStatus,
                  deleteStatus == 200
                      ? QByteArray("{\"deleted\":true}")
                      : QByteArray("{\"error\":\"cleanup failed\"}"));
        remove->deleteLater();

        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *create = server.nextPendingConnection();
        const QByteArray createRequest = readRequest(create);
        QVERIFY(createRequest.startsWith("POST /v1/conversations "));
        QCOMPARE(client.pendingResources().size(), 0);
        replyJson(create, 201, "{\"conversation_id\":\"meo:new-resource-chat\"}");
        create->deleteLater();

        QTRY_VERIFY(!client.actionBusy());
        QTRY_COMPARE(client.pendingResources().size(), 0);
        QVERIFY(client.status().contains(QStringLiteral("Ready")));
        QSettings().clear();
        qunsetenv("MEO_AI_SERVICE_ENDPOINT");
    }

private slots:
    void initTestCase() {
        QCoreApplication::setOrganizationName("MeoArchNewChatResourceTest");
        QCoreApplication::setApplicationName("MeoAINewChatResourceTest");
    }

    void cleanup() {
        QSettings().clear();
        qunsetenv("MEO_AI_SERVICE_ENDPOINT");
    }

    void successfulDeletePrecedesNewConversation() {
        expectNewChatAfterDeleteResult(200);
    }

    void failedDeleteStillAbandonsOldConversationIdentity() {
        expectNewChatAfterDeleteResult(503);
    }
};

QTEST_GUILESS_MAIN(NewChatResourceTest)
#include "new-chat-resource-test.moc"

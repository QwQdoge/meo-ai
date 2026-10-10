#include "agentclient.h"
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSettings>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTest>

class ResourceClientTest : public QObject {
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
        const QByteArray statusText = status == 201 ? "201 Created" : "200 OK";
        socket->write("HTTP/1.1 " + statusText
                      + "\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                      + QByteArray::number(body.size()) + "\r\n\r\n" + body);
        socket->flush();
        socket->disconnectFromHost();
    }

private slots:
    void initTestCase() {
        QCoreApplication::setOrganizationName("MeoArchResourceClientTest");
        QCoreApplication::setApplicationName("MeoAIResourceClientTest");
    }

    void cleanup() {
        QSettings().clear();
        qunsetenv("MEO_AI_SERVICE_ENDPOINT");
    }

    void longPasteIsCreatedAndSentByOpaqueResourceId() {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());
        QSettings().clear();

        AgentClient client;
        client.addLongTextResource("research.txt", "alpha beta gamma");

        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *createConversation = server.nextPendingConnection();
        const QByteArray conversationRequest = readRequest(createConversation);
        QVERIFY(conversationRequest.startsWith("POST /v1/conversations "));
        replyJson(createConversation, 201, "{\"conversation_id\":\"meo:resources\"}");

        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *createResource = server.nextPendingConnection();
        const QByteArray resourceRequest = readRequest(createResource);
        QVERIFY(resourceRequest.contains("POST /v1/conversations/meo:resources/resources/text"));
        const auto resourceBody = QJsonDocument::fromJson(
            resourceRequest.mid(resourceRequest.indexOf("\r\n\r\n") + 4)).object();
        QCOMPARE(resourceBody.value("name").toString(), QString("research.txt"));
        QCOMPARE(resourceBody.value("text").toString(), QString("alpha beta gamma"));
        replyJson(
            createResource,
            201,
            "{\"conversation_id\":\"meo:resources\",\"resource\":{\"resource_id\":\"resource:0123456789abcdef0123456789abcdef\",\"kind\":\"long_text\",\"name\":\"research.txt\",\"mime_type\":\"text/plain; charset=utf-8\",\"size_bytes\":16,\"sha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"state\":\"ready\"}}");

        QTRY_COMPARE(client.pendingResources().size(), 1);
        QCOMPARE(client.pendingResources().at(0).toMap().value("name").toString(), QString("research.txt"));

        client.sendWithPendingResources("Use the attached notes");
        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *message = server.nextPendingConnection();
        const QByteArray messageRequest = readRequest(message);
        QVERIFY(messageRequest.contains("POST /v1/conversations/meo:resources/messages"));
        const auto messageBody = QJsonDocument::fromJson(
            messageRequest.mid(messageRequest.indexOf("\r\n\r\n") + 4)).object();
        QCOMPARE(messageBody.value("text").toString(), QString("Use the attached notes"));
        const auto ids = messageBody.value("resource_ids").toArray();
        QCOMPARE(ids.size(), 1);
        QCOMPARE(ids.at(0).toString(), QString("resource:0123456789abcdef0123456789abcdef"));
        QCOMPARE(client.pendingResources().size(), 0);

        message->write("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\nX-Meo-Request-Id: req-resource\r\n\r\n");
        message->write("data: {\"seq\":1,\"type\":\"request.started\",\"request_id\":\"req-resource\",\"conversation_id\":\"meo:resources\",\"state\":\"running_model\"}\n\n");
        message->write("data: {\"seq\":2,\"type\":\"request.completed\",\"request_id\":\"req-resource\",\"state\":\"completed\"}\n\n");
        message->flush();
        message->disconnectFromHost();
        QTRY_VERIFY(!client.busy());
        QVERIFY(client.status().contains("Ready"));

        createConversation->deleteLater();
        createResource->deleteLater();
        message->deleteLater();
    }
};

QTEST_GUILESS_MAIN(ResourceClientTest)
#include "resource-client-test.moc"

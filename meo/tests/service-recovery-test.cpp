#include "agentclient.h"
#include <QTcpServer>
#include <QTcpSocket>
#include <QTest>

class ServiceRecoveryTest : public QObject {
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

    static void replyJson(QTcpSocket *socket, int status, const QByteArray &reason, const QByteArray &body) {
        socket->write("HTTP/1.1 " + QByteArray::number(status) + " " + reason
                      + "\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                      + QByteArray::number(body.size()) + "\r\n\r\n" + body);
        socket->flush();
        socket->disconnectFromHost();
    }

    static void createConversation(QTcpServer &server, AgentClient &client, const QByteArray &id) {
        client.newChat();
        QTRY_VERIFY(server.hasPendingConnections());
        auto create = server.nextPendingConnection();
        readRequest(create);
        const QByteArray body = "{\"conversation_id\":\"" + id + "\"}";
        replyJson(create, 201, "Created", body);
        QTRY_VERIFY(!client.actionBusy());
        create->deleteLater();
    }

    static void openToolWait(QTcpServer &server, AgentClient &client,
                             const QByteArray &conversationId,
                             const QByteArray &requestId,
                             const QByteArray &decisionId,
                             QTcpSocket *&stream) {
        client.send("needs tool");
        QTRY_VERIFY(server.hasPendingConnections());
        stream = server.nextPendingConnection();
        QVERIFY(stream != nullptr);
        readRequest(stream);
        stream->write("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\nX-Meo-Request-Id: "
                      + requestId + "\r\n\r\n");
        stream->write("data: {\"seq\":1,\"type\":\"request.started\",\"request_id\":\""
                      + requestId + "\",\"conversation_id\":\"" + conversationId
                      + "\",\"state\":\"running_model\"}\n\n");
        stream->write("data: {\"seq\":2,\"type\":\"tool.requested\",\"request_id\":\""
                      + requestId + "\",\"conversation_id\":\"" + conversationId
                      + "\",\"decision_id\":\"" + decisionId
                      + "\",\"tool_name\":\"terminal\",\"options\":[{\"index\":0,\"title\":\"Deny\"},{\"index\":1,\"title\":\"Approve\"}]}\n\n");
        stream->flush();
        QTRY_COMPARE(client.options().size(), 2);
    }

private slots:
    void missingRequestAfterRestartClearsStaleDecision() {
        qunsetenv("MEO_AI_ENDPOINT");
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());

        AgentClient client;
        createConversation(server, client, "meo:restart");
        QTcpSocket *stream = nullptr;
        openToolWait(server, client, "meo:restart", "req-old", "dec-old", stream);
        QVERIFY(stream != nullptr);
        stream->disconnectFromHost();

        QTRY_VERIFY(server.hasPendingConnections());
        auto reconnect = server.nextPendingConnection();
        const QByteArray request = readRequest(reconnect);
        QVERIFY(request.contains("GET /v1/requests/req-old/events?after=2"));
        replyJson(reconnect, 404, "Not Found", "{\"error\":\"unknown request\"}");

        QTRY_COMPARE(client.options().size(), 0);
        QTRY_VERIFY(!client.busy());
        QVERIFY(client.status().contains("no longer exists"));

        // Recovery must leave the UI usable instead of trapping it behind a
        // stale tool confirmation card.
        client.newChat();
        QTRY_VERIFY(server.hasPendingConnections());
        auto createAgain = server.nextPendingConnection();
        const QByteArray createRequest = readRequest(createAgain);
        QVERIFY(createRequest.contains("POST /v1/conversations"));
        replyJson(createAgain, 201, "Created", "{\"conversation_id\":\"meo:after-restart\"}");
        QTRY_VERIFY(!client.actionBusy());

        stream->deleteLater();
        reconnect->deleteLater();
        createAgain->deleteLater();
        qunsetenv("MEO_AI_SERVICE_ENDPOINT");
    }

    void journalGapCancelsInsteadOfReusingStaleDecision() {
        qunsetenv("MEO_AI_ENDPOINT");
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());

        AgentClient client;
        createConversation(server, client, "meo:gap");
        QTcpSocket *stream = nullptr;
        openToolWait(server, client, "meo:gap", "req-gap", "dec-gap", stream);
        QVERIFY(stream != nullptr);
        stream->disconnectFromHost();

        QTRY_VERIFY(server.hasPendingConnections());
        auto reconnect = server.nextPendingConnection();
        const QByteArray request = readRequest(reconnect);
        QVERIFY(request.contains("GET /v1/requests/req-gap/events?after=2"));
        replyJson(reconnect, 409, "Conflict", "{\"error\":\"event history gap\"}");

        QTRY_COMPARE(client.options().size(), 0);
        QTRY_VERIFY(server.hasPendingConnections());
        auto cancel = server.nextPendingConnection();
        const QByteArray cancelRequest = readRequest(cancel);
        QVERIFY(cancelRequest.contains("POST /v1/requests/req-gap/cancel"));
        replyJson(cancel, 200, "OK",
                  "{\"accepted\":true,\"request_id\":\"req-gap\",\"state\":\"cancel_requested\"}");
        QTRY_VERIFY(!client.actionBusy());
        QVERIFY(client.status().contains("Stopping"));

        stream->deleteLater();
        reconnect->deleteLater();
        cancel->deleteLater();
        qunsetenv("MEO_AI_SERVICE_ENDPOINT");
    }
};

QTEST_GUILESS_MAIN(ServiceRecoveryTest)
#include "service-recovery-test.moc"

#include "agentclient.h"
#include <QTcpServer>
#include <QTcpSocket>
#include <QTest>

class EarlyCancelTest : public QObject {
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

private slots:
    void cancelBeforeRequestIdIsKnown() {
        qunsetenv("MEO_AI_ENDPOINT");
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());

        AgentClient client;
        QVERIFY(client.serviceMode());
        client.newChat();

        QTRY_VERIFY(server.hasPendingConnections());
        auto create = server.nextPendingConnection();
        readRequest(create);
        const QByteArray createBody = "{\"conversation_id\":\"meo:early-cancel\"}";
        create->write("HTTP/1.1 201 Created\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                      + QByteArray::number(createBody.size()) + "\r\n\r\n" + createBody);
        create->flush();
        create->disconnectFromHost();
        QTRY_VERIFY(!client.actionBusy());

        client.send("long task");
        QTRY_VERIFY(server.hasPendingConnections());
        auto stream = server.nextPendingConnection();
        const QByteArray messageRequest = readRequest(stream);
        QVERIFY(messageRequest.contains("POST /v1/conversations/meo:early-cancel/messages"));
        QVERIFY(client.busy());

        // Cancel before the response headers expose X-Meo-Request-Id.
        client.cancel();
        QVERIFY(client.busy());
        QVERIFY(client.status().contains("Stopping"));
        QVERIFY(!server.hasPendingConnections());

        // Once the request id arrives, the queued cancel must be submitted
        // automatically; the user must not have to press Stop a second time.
        stream->write("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\nX-Meo-Request-Id: req-early\r\n\r\n");
        stream->flush();

        QTRY_VERIFY(server.hasPendingConnections());
        auto cancel = server.nextPendingConnection();
        const QByteArray cancelRequest = readRequest(cancel);
        QVERIFY(cancelRequest.contains("POST /v1/requests/req-early/cancel"));

        const QByteArray accepted =
            "{\"accepted\":true,\"request_id\":\"req-early\",\"state\":\"cancel_requested\"}";
        cancel->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                      + QByteArray::number(accepted.size()) + "\r\n\r\n" + accepted);
        cancel->flush();
        cancel->disconnectFromHost();

        stream->write("data: {\"seq\":1,\"type\":\"request.started\",\"request_id\":\"req-early\",\"conversation_id\":\"meo:early-cancel\",\"state\":\"cancel_requested\"}\n\n");
        stream->write("data: {\"seq\":2,\"type\":\"request.cancelled\",\"request_id\":\"req-early\",\"state\":\"cancelled\"}\n\n");
        stream->flush();
        stream->disconnectFromHost();

        QTRY_VERIFY(!client.busy());
        QVERIFY(client.status().contains("Stopped"));

        create->deleteLater();
        stream->deleteLater();
        cancel->deleteLater();
        qunsetenv("MEO_AI_SERVICE_ENDPOINT");
    }
};

QTEST_GUILESS_MAIN(EarlyCancelTest)
#include "early-cancel-test.moc"

#include "agentclient.h"
#include <QJsonDocument>
#include <QJsonObject>
#include <QTcpServer>
#include <QTcpSocket>
#include <QSignalSpy>
#include <QTest>

class ClientTest : public QObject {
    Q_OBJECT
private:
    static QByteArray readRequest(QTcpSocket *socket) {
        QByteArray request;
        for (int i = 0; i < 100 && !request.contains("\r\n\r\n"); ++i) {
            if (!socket->bytesAvailable()) socket->waitForReadyRead(30);
            request += socket->readAll();
        }
        const int headerEnd = request.indexOf("\r\n\r\n");
        if (headerEnd >= 0) {
            const auto headers = request.left(headerEnd);
            const auto marker = QByteArray("Content-Length:");
            const int start = headers.toLower().indexOf(marker.toLower());
            if (start >= 0) {
                const int valueStart = start + marker.size();
                const int valueEnd = headers.indexOf("\r\n", valueStart);
                const int length = headers.mid(valueStart, valueEnd - valueStart).trimmed().toInt();
                while (request.size() - headerEnd - 4 < length) {
                    if (!socket->waitForReadyRead(30)) break;
                    request += socket->readAll();
                }
            }
        }
        return request;
    }

private slots:
    void fragmentedStreamAndInteraction() {
        qunsetenv("MEO_AI_SERVICE_ENDPOINT");
        QTcpServer server; QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_ENDPOINT", QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());
        qputenv("MEO_AI_API_KEY", "test-secret");
        AgentClient client;
        QVERIFY(!client.serviceMode());
        QSignalSpy chunks(&client, &AgentClient::delta);
        QSignalSpy tools(&client, &AgentClient::toolEvent);
        client.send("hello");
        QTRY_VERIFY(server.hasPendingConnections());
        auto socket = server.nextPendingConnection();
        QByteArray request = readRequest(socket);
        QVERIFY(request.contains("hello"));
        QVERIFY(request.contains("Bearer test-secret"));
        QVERIFY(request.contains("meo:"));
        const QByteArray body = "data: {\"choices\":[{\"delta\":{\"content\":\"你好\"}}]}\r\n\r\ndata: {\"choices\":[{\"delta\":{\"meo_event\":{\"type\":\"tool_interaction\",\"tool_name\":\"read_file\",\"options\":[{\"index\":0,\"title\":\"Allow\"},{\"index\":1,\"title\":\"Deny\"}]}}}]}\n\ndata: [DONE]\n\n";
        socket->write("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\nContent-Length: " + QByteArray::number(body.size()) + "\r\n\r\n" + body.left(23)); socket->flush();
        QTest::qWait(20);
        socket->write(body.mid(23)); socket->flush();
        QTRY_VERIFY(!client.busy());
        QCOMPARE(chunks.size(), 1); QCOMPARE(chunks[0][0].toString(), QString::fromUtf8("你好"));
        QCOMPARE(tools.size(), 1); QCOMPARE(client.options().size(), 2);
        client.choose(2); QVERIFY(!client.busy());
        client.send("ignore confirmation"); QVERIFY(!client.busy());
        client.choose(1);
        QTRY_VERIFY(server.hasPendingConnections());
        auto choice = server.nextPendingConnection();
        QByteArray selection = readRequest(choice);
        QVERIFY(selection.contains("/option 2"));
        const auto first = QJsonDocument::fromJson(request.mid(request.indexOf("\r\n\r\n") + 4)).object();
        const auto second = QJsonDocument::fromJson(selection.mid(selection.indexOf("\r\n\r\n") + 4)).object();
        QCOMPARE(first.value("user"), second.value("user"));
        const QByteArray done = "data: [DONE]\n\n";
        choice->write("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\nContent-Length: " + QByteArray::number(done.size()) + "\r\n\r\n" + done); choice->flush();
        QTRY_VERIFY(!client.busy());
        socket->deleteLater(); choice->deleteLater();
    }

    void serviceDecisionWhileStreamIsOpen() {
        qunsetenv("MEO_AI_ENDPOINT");
        QTcpServer server; QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT", QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());
        AgentClient client;
        QVERIFY(client.serviceMode());
        QSignalSpy chunks(&client, &AgentClient::delta);
        client.send("hello service");

        QTRY_VERIFY(server.hasPendingConnections());
        auto create = server.nextPendingConnection();
        const QByteArray createRequest = readRequest(create);
        QVERIFY(createRequest.startsWith("POST /v1/conversations "));
        const QByteArray createBody = "{\"conversation_id\":\"meo:test\"}";
        create->write("HTTP/1.1 201 Created\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: " + QByteArray::number(createBody.size()) + "\r\n\r\n" + createBody);
        create->flush(); create->disconnectFromHost();

        QTRY_VERIFY(server.hasPendingConnections());
        auto stream = server.nextPendingConnection();
        const QByteArray messageRequest = readRequest(stream);
        QVERIFY(messageRequest.contains("POST /v1/conversations/meo:test/messages"));
        QVERIFY(messageRequest.contains("hello service"));
        stream->write("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\nX-Meo-Request-Id: req-1\r\n\r\n");
        stream->write("data: {\"type\":\"request.started\",\"request_id\":\"req-1\",\"conversation_id\":\"meo:test\",\"state\":\"running_model\"}\n\n");
        stream->write("data: {\"type\":\"message.delta\",\"request_id\":\"req-1\",\"conversation_id\":\"meo:test\",\"delta\":\"hello\"}\n\n");
        stream->write("data: {\"type\":\"tool.requested\",\"request_id\":\"req-1\",\"conversation_id\":\"meo:test\",\"decision_id\":\"dec-1\",\"tool_name\":\"terminal\",\"options\":[{\"index\":0,\"title\":\"Deny\"},{\"index\":1,\"title\":\"Approve\"}]}\n\n");
        stream->flush();

        QTRY_COMPARE(client.options().size(), 2);
        QVERIFY(client.busy());
        QCOMPARE(chunks.size(), 1);
        client.choose(1);
        QTRY_VERIFY(server.hasPendingConnections());
        auto decision = server.nextPendingConnection();
        const QByteArray decisionRequest = readRequest(decision);
        QVERIFY(decisionRequest.contains("POST /v1/requests/req-1/decisions/dec-1"));
        QVERIFY(decisionRequest.contains("\"option_index\":1"));
        const QByteArray accepted = "{\"accepted\":true,\"request_id\":\"req-1\",\"state\":\"running_tool\"}";
        decision->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: " + QByteArray::number(accepted.size()) + "\r\n\r\n" + accepted);
        decision->flush(); decision->disconnectFromHost();
        QTRY_COMPARE(client.options().size(), 0);
        QVERIFY(client.busy());

        stream->write("data: {\"type\":\"request.completed\",\"request_id\":\"req-1\",\"state\":\"completed\"}\n\n");
        stream->flush(); stream->disconnectFromHost();
        QTRY_VERIFY(!client.busy());
        QVERIFY(client.status().contains("Ready"));
        create->deleteLater(); stream->deleteLater(); decision->deleteLater();
    }

    void serviceCancelUsesDedicatedEndpoint() {
        qunsetenv("MEO_AI_ENDPOINT");
        QTcpServer server; QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT", QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());
        AgentClient client;
        client.newChat();
        QTRY_VERIFY(server.hasPendingConnections());
        auto create = server.nextPendingConnection();
        readRequest(create);
        const QByteArray createBody = "{\"conversation_id\":\"meo:cancel\"}";
        create->write("HTTP/1.1 201 Created\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: " + QByteArray::number(createBody.size()) + "\r\n\r\n" + createBody);
        create->flush(); create->disconnectFromHost();
        QTRY_VERIFY(!client.actionBusy());

        client.send("long task");
        QTRY_VERIFY(server.hasPendingConnections());
        auto stream = server.nextPendingConnection();
        readRequest(stream);
        stream->write("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\nX-Meo-Request-Id: req-cancel\r\n\r\n");
        stream->write("data: {\"type\":\"request.started\",\"request_id\":\"req-cancel\",\"conversation_id\":\"meo:cancel\",\"state\":\"running_model\"}\n\n");
        stream->flush();
        QTRY_VERIFY(client.busy());
        client.cancel();
        QTRY_VERIFY(server.hasPendingConnections());
        auto cancel = server.nextPendingConnection();
        const QByteArray cancelRequest = readRequest(cancel);
        QVERIFY(cancelRequest.contains("POST /v1/requests/req-cancel/cancel"));
        const QByteArray accepted = "{\"accepted\":true,\"request_id\":\"req-cancel\",\"state\":\"cancel_requested\"}";
        cancel->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: " + QByteArray::number(accepted.size()) + "\r\n\r\n" + accepted);
        cancel->flush(); cancel->disconnectFromHost();
        stream->write("data: {\"type\":\"request.cancelled\",\"request_id\":\"req-cancel\",\"state\":\"cancelled\"}\n\n");
        stream->flush(); stream->disconnectFromHost();
        QTRY_VERIFY(!client.busy());
        QVERIFY(client.status().contains("Stopped"));
        create->deleteLater(); stream->deleteLater(); cancel->deleteLater();
    }

    void rejectRemoteEndpoint() {
        qunsetenv("MEO_AI_SERVICE_ENDPOINT");
        qputenv("MEO_AI_ENDPOINT", "http://example.com:8080");
        AgentClient client; client.send("private text");
        QVERIFY(!client.busy()); QVERIFY(client.status().contains("loopback"));
    }

    void rejectRemoteServiceEndpoint() {
        qputenv("MEO_AI_SERVICE_ENDPOINT", "http://example.com:8765");
        AgentClient client; client.send("private text");
        QVERIFY(!client.busy()); QVERIFY(client.status().contains("loopback"));
        qunsetenv("MEO_AI_SERVICE_ENDPOINT");
    }

    void connectionFailure() {
        qunsetenv("MEO_AI_SERVICE_ENDPOINT");
        QTcpServer server; QVERIFY(server.listen(QHostAddress::LocalHost));
        const auto port=server.serverPort(); server.close();
        qputenv("MEO_AI_ENDPOINT", QString("http://127.0.0.1:%1").arg(port).toUtf8());
        AgentClient client; client.send("hello");
        QTRY_VERIFY(!client.busy()); QVERIFY(client.status().contains("unavailable"));
    }
};
QTEST_GUILESS_MAIN(ClientTest)
#include "client-test.moc"

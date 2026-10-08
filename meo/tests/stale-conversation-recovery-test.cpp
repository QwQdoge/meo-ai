#include "agentclient.h"
#include <QSettings>
#include <QSignalSpy>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTest>

class StaleConversationRecoveryTest : public QObject {
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
            const QByteArray headers = request.left(headerEnd);
            const QByteArray marker = "Content-Length:";
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

    static void replyJson(QTcpSocket *socket, int status, const QByteArray &reason, const QByteArray &body) {
        socket->write("HTTP/1.1 " + QByteArray::number(status) + " " + reason
                      + "\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                      + QByteArray::number(body.size()) + "\r\n\r\n" + body);
        socket->flush();
        socket->disconnectFromHost();
    }

private slots:
    void initTestCase() {
        QCoreApplication::setOrganizationName("MeoArchStaleRecoveryTest");
        QCoreApplication::setApplicationName("MeoAIStaleRecoveryTest");
    }

    void cleanup() {
        QSettings().clear();
        qunsetenv("MEO_AI_SERVICE_ENDPOINT");
        qunsetenv("MEO_AI_ENDPOINT");
    }

    void retriesOnceOnlyWhenStaleConversationWasRejectedBeforeStart() {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());
        QSettings settings;
        settings.clear();
        settings.setValue("serviceConversationId", "meo:stale");
        settings.sync();

        AgentClient client;
        QSignalSpy messageSpy(&client, &AgentClient::message);
        QSignalSpy deltaSpy(&client, &AgentClient::delta);

        // Startup history lookup is temporarily unavailable, so the persisted
        // identity remains and the later send exercises stale-ID recovery.
        QTRY_VERIFY(server.hasPendingConnections());
        auto history = server.nextPendingConnection();
        const QByteArray historyRequest = readRequest(history);
        QVERIFY(historyRequest.contains("GET /v1/conversations/meo:stale/messages"));
        replyJson(history, 503, "Service Unavailable", "{\"error\":\"temporary\"}");
        QTRY_VERIFY(!client.actionBusy());

        client.send("recover this message");
        QTRY_VERIFY(server.hasPendingConnections());
        auto staleSend = server.nextPendingConnection();
        const QByteArray staleRequest = readRequest(staleSend);
        QVERIFY(staleRequest.contains("POST /v1/conversations/meo:stale/messages"));
        QVERIFY(staleRequest.contains("recover this message"));
        replyJson(staleSend, 404, "Not Found", "{\"error\":\"unknown conversation_id\"}");

        // The precise pre-start 404 may be recovered once by creating a new
        // conversation. No user or assistant placeholder is emitted again.
        QTRY_VERIFY(server.hasPendingConnections());
        auto create = server.nextPendingConnection();
        const QByteArray createRequest = readRequest(create);
        QVERIFY(createRequest.startsWith("POST /v1/conversations "));
        replyJson(create, 201, "Created", "{\"conversation_id\":\"meo:fresh\"}");

        QTRY_VERIFY(server.hasPendingConnections());
        auto retry = server.nextPendingConnection();
        const QByteArray retryRequest = readRequest(retry);
        QVERIFY(retryRequest.contains("POST /v1/conversations/meo:fresh/messages"));
        QVERIFY(retryRequest.contains("recover this message"));
        retry->write("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\n"
                     "X-Meo-Request-Id: req-recovered\r\n\r\n");
        retry->write("data: {\"seq\":1,\"type\":\"request.started\",\"request_id\":\"req-recovered\",\"conversation_id\":\"meo:fresh\",\"state\":\"running_model\"}\n\n");
        retry->write("data: {\"seq\":2,\"type\":\"message.delta\",\"request_id\":\"req-recovered\",\"conversation_id\":\"meo:fresh\",\"delta\":\"recovered\"}\n\n");
        retry->write("data: {\"seq\":3,\"type\":\"request.completed\",\"request_id\":\"req-recovered\",\"state\":\"completed\"}\n\n");
        retry->flush();
        retry->disconnectFromHost();

        QTRY_VERIFY(!client.busy());
        QCOMPARE(messageSpy.count(), 2);
        QCOMPARE(messageSpy.at(0).at(0).toString(), QString("user"));
        QCOMPARE(messageSpy.at(0).at(1).toString(), QString("recover this message"));
        QCOMPARE(messageSpy.at(1).at(0).toString(), QString("assistant"));
        QCOMPARE(messageSpy.at(1).at(1).toString(), QString(""));
        QCOMPARE(deltaSpy.count(), 1);
        QCOMPARE(deltaSpy.at(0).at(0).toString(), QString("recovered"));
        QCOMPARE(QSettings().value("serviceConversationId").toString(), QString("meo:fresh"));
        QVERIFY(client.status().contains("Ready"));

        history->deleteLater();
        staleSend->deleteLater();
        create->deleteLater();
        retry->deleteLater();
    }
};

QTEST_GUILESS_MAIN(StaleConversationRecoveryTest)
#include "stale-conversation-recovery-test.moc"

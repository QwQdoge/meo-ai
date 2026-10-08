#include "agentclient.h"
#include <QJsonDocument>
#include <QJsonObject>
#include <QTcpServer>
#include <QTcpSocket>
#include <QSignalSpy>
#include <QTest>

class ClientTest : public QObject {
    Q_OBJECT
private slots:
    void fragmentedStreamAndInteraction() {
        QTcpServer server; QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_ENDPOINT", QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());
        qputenv("MEO_AI_API_KEY", "test-secret");
        AgentClient client;
        QSignalSpy chunks(&client, &AgentClient::delta);
        QSignalSpy tools(&client, &AgentClient::toolEvent);
        client.send("hello");
        QTRY_VERIFY(server.hasPendingConnections());
        auto socket = server.nextPendingConnection();
        QTRY_VERIFY(socket->bytesAvailable() > 0);
        QByteArray request = socket->readAll();
        QTRY_VERIFY_WITH_TIMEOUT((request += socket->readAll()).contains("hello"), 3000);
        QVERIFY(request.contains("Bearer test-secret"));
        QVERIFY(request.contains("meo:"));
        const QByteArray body = "data: {\"choices\":[{\"delta\":{\"content\":\"你好\"}}]}\r\n\r\ndata: {\"choices\":[{\"delta\":{\"meo_event\":{\"type\":\"tool_interaction\",\"tool_name\":\"read_file\",\"options\":[{\"index\":0,\"title\":\"Allow\"},{\"index\":1,\"title\":\"Deny\"}]}}}]}\n\ndata: [DONE]\n\n";
        socket->write("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\nContent-Length: " + QByteArray::number(body.size()) + "\r\n\r\n" + body.left(23)); socket->flush();
        QTest::qWait(20);
        socket->write(body.mid(23)); socket->flush();
        QTRY_VERIFY(!client.busy());
        QCOMPARE(chunks.size(), 1); QCOMPARE(chunks[0][0].toString(), QString::fromUtf8("你好"));
        QCOMPARE(tools.size(), 1); QCOMPARE(client.options().size(), 2);
        client.choose(2); QVERIFY(!client.busy()); // invalid choice cannot submit
        client.send("ignore confirmation"); QVERIFY(!client.busy());
        client.choose(1);
        QTRY_VERIFY(server.hasPendingConnections());
        auto choice = server.nextPendingConnection();
        QTRY_VERIFY(choice->bytesAvailable() > 0);
        QByteArray selection = choice->readAll();
        QTRY_VERIFY_WITH_TIMEOUT((selection += choice->readAll()).contains("/option 2"), 3000);
        const auto first = QJsonDocument::fromJson(request.mid(request.indexOf("\r\n\r\n") + 4)).object();
        const auto second = QJsonDocument::fromJson(selection.mid(selection.indexOf("\r\n\r\n") + 4)).object();
        QCOMPARE(first.value("user"), second.value("user"));
        const QByteArray done = "data: [DONE]\n\n";
        choice->write("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\nContent-Length: " + QByteArray::number(done.size()) + "\r\n\r\n" + done); choice->flush();
        QTRY_VERIFY(!client.busy());
        socket->deleteLater(); choice->deleteLater();
    }
    void rejectRemoteEndpoint() {
        qputenv("MEO_AI_ENDPOINT", "http://example.com:8080");
        AgentClient client; client.send("private text");
        QVERIFY(!client.busy()); QVERIFY(client.status().contains("loopback"));
    }
    void connectionFailure() {
        QTcpServer server; QVERIFY(server.listen(QHostAddress::LocalHost));
        const auto port=server.serverPort(); server.close();
        qputenv("MEO_AI_ENDPOINT", QString("http://127.0.0.1:%1").arg(port).toUtf8());
        AgentClient client; client.send("hello");
        QTRY_VERIFY(!client.busy()); QVERIFY(client.status().contains("unavailable"));
    }
};
QTEST_GUILESS_MAIN(ClientTest)
#include "client-test.moc"

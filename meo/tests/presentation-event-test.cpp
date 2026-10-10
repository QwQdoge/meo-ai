#include "agentclient.h"
#include <QSettings>
#include <QSignalSpy>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
#include <QTest>

class PresentationEventTest final : public QObject {
    Q_OBJECT
private:
    QTemporaryDir settingsDirectory;

    static QByteArray readRequest(QTcpSocket *socket) {
        QByteArray request;
        for (int i = 0; i < 100 && !request.contains("\r\n\r\n"); ++i) {
            if (!socket->bytesAvailable()) socket->waitForReadyRead(30);
            request += socket->readAll();
        }
        const int headerEnd = request.indexOf("\r\n\r\n");
        if (headerEnd < 0) return request;
        const QByteArray headers = request.left(headerEnd);
        const int contentLengthPos = headers.toLower().indexOf("content-length:");
        if (contentLengthPos < 0) return request;
        const int valueStart = contentLengthPos + QByteArray("content-length:").size();
        const int valueEnd = headers.indexOf("\r\n", valueStart);
        const int expected = headers.mid(valueStart, valueEnd - valueStart).trimmed().toInt();
        while (request.size() - headerEnd - 4 < expected) {
            if (!socket->waitForReadyRead(30)) break;
            request += socket->readAll();
        }
        return request;
    }

private slots:
    void initTestCase() {
        QVERIFY(settingsDirectory.isValid());
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, settingsDirectory.path());
    }

    void cleanup() {
        QSettings().clear();
        qunsetenv("MEO_AI_SERVICE_ENDPOINT");
        qunsetenv("MEO_AI_ENDPOINT");
    }

    void dispatchesNativePresentationCardWithoutTurningItIntoToolApproval() {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());
        QSettings().clear();

        AgentClient client;
        QVERIFY(client.serviceMode());
        QSignalSpy cards(&client, &AgentClient::presentationEvent);
        QSignalSpy toolEvents(&client, &AgentClient::toolEvent);

        client.newChat();
        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *create = server.nextPendingConnection();
        const QByteArray createRequest = readRequest(create);
        QVERIFY(createRequest.startsWith("POST /v1/conversations "));
        const QByteArray createBody = "{\"conversation_id\":\"meo:cards\"}";
        create->write("HTTP/1.1 201 Created\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                      + QByteArray::number(createBody.size()) + "\r\n\r\n" + createBody);
        create->flush();
        create->disconnectFromHost();
        QTRY_VERIFY(!client.actionBusy());

        client.send("show my build status");
        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *stream = server.nextPendingConnection();
        const QByteArray sendRequest = readRequest(stream);
        QVERIFY(sendRequest.contains("POST /v1/conversations/meo:cards/messages"));
        stream->write("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\nX-Meo-Request-Id: req-card\r\n\r\n");
        stream->write("data: {\"seq\":1,\"type\":\"request.started\",\"request_id\":\"req-card\",\"conversation_id\":\"meo:cards\",\"state\":\"running_model\"}\n\n");
        stream->write("data: {\"seq\":2,\"type\":\"presentation.card\",\"request_id\":\"req-card\",\"conversation_id\":\"meo:cards\",\"card\":{\"card_id\":\"build:preview\",\"kind\":\"status\",\"title\":\"Native build\",\"subtitle\":\"Meo AI\",\"value\":\"Passing\",\"detail\":\"All preview checks passed.\"}}\n\n");
        stream->write("data: {\"seq\":3,\"type\":\"request.completed\",\"request_id\":\"req-card\",\"state\":\"completed\"}\n\n");
        stream->flush();
        stream->disconnectFromHost();

        QTRY_COMPARE(cards.size(), 1);
        QTRY_VERIFY(!client.busy());
        QCOMPARE(toolEvents.size(), 0);
        const QVariantMap event = cards.first().first().toMap();
        QCOMPARE(event.value("type").toString(), QString("presentation.card"));
        const QVariantMap card = event.value("card").toMap();
        QCOMPARE(card.value("kind").toString(), QString("status"));
        QCOMPARE(card.value("title").toString(), QString("Native build"));
        QCOMPARE(card.value("value").toString(), QString("Passing"));
        QVERIFY(client.options().isEmpty());

        create->deleteLater();
        stream->deleteLater();
    }
};

QTEST_GUILESS_MAIN(PresentationEventTest)
#include "presentation-event-test.moc"

#include "agentclient.h"
#include <QSettings>
#include <QSignalSpy>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTest>

class HistoryRestoreTest : public QObject {
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

    static void prepareSettings(const QString &conversationId) {
        QSettings settings;
        settings.clear();
        settings.setValue("serviceConversationId", conversationId);
        settings.sync();
    }

private slots:
    void initTestCase() {
        QCoreApplication::setOrganizationName("MeoArchHistoryTest");
        QCoreApplication::setApplicationName("MeoAIHistoryTest");
    }

    void cleanup() {
        QSettings().clear();
        qunsetenv("MEO_AI_SERVICE_ENDPOINT");
        qunsetenv("MEO_AI_ENDPOINT");
    }

    void restoresSavedConversationIntoNativeSignals() {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());
        prepareSettings("meo:history");

        AgentClient client;
        QSignalSpy resetSpy(&client, &AgentClient::resetChat);
        QSignalSpy messageSpy(&client, &AgentClient::message);
        QSignalSpy metadataSpy(&client, &AgentClient::conversationMetadata);
        QStringList order;
        connect(&client, &AgentClient::resetChat, this, [&order] {
            order.append(QStringLiteral("reset"));
        });
        connect(&client, &AgentClient::message, this,
                [&order](const QString &role, const QString &) {
            order.append(QStringLiteral("message:") + role);
        });
        connect(&client, &AgentClient::conversationMetadata, this,
                [&order](const QVariantMap &) {
            order.append(QStringLiteral("metadata"));
        });

        QTRY_VERIFY(server.hasPendingConnections());
        auto socket = server.nextPendingConnection();
        const QByteArray request = readRequest(socket);
        QVERIFY(request.contains("GET /v1/conversations/meo:history/messages"));
        replyJson(socket, 200, "OK",
                  "{\"conversation_id\":\"meo:history\","
                  "\"conversation\":{\"conversation_id\":\"meo:history\","
                  "\"title\":\"Project Review\","
                  "\"summary\":\"Reviewed the Meo AI project and next steps.\","
                  "\"title_is_default\":false,\"title_is_automatic\":false},"
                  "\"messages\":["
                  "{\"role\":\"user\",\"text\":\"hello\"},"
                  "{\"role\":\"assistant\",\"text\":\"Hi again\"}]}" );

        QTRY_COMPARE(resetSpy.count(), 1);
        QTRY_COMPARE(messageSpy.count(), 2);
        QTRY_COMPARE(metadataSpy.count(), 1);
        QCOMPARE(messageSpy.at(0).at(0).toString(), QString("user"));
        QCOMPARE(messageSpy.at(0).at(1).toString(), QString("hello"));
        QCOMPARE(messageSpy.at(1).at(0).toString(), QString("assistant"));
        QCOMPARE(messageSpy.at(1).at(1).toString(), QString("Hi again"));
        const QVariantMap metadata = metadataSpy.at(0).at(0).toMap();
        QCOMPARE(metadata.value("conversation_id").toString(), QString("meo:history"));
        QCOMPARE(metadata.value("title").toString(), QString("Project Review"));
        QCOMPARE(metadata.value("summary").toString(),
                 QString("Reviewed the Meo AI project and next steps."));
        QCOMPARE(order, QStringList({
            QStringLiteral("reset"),
            QStringLiteral("message:user"),
            QStringLiteral("message:assistant"),
            QStringLiteral("metadata"),
        }));
        QTRY_COMPARE(client.status(), QString("Ready"));
        socket->deleteLater();
    }

    void legacyHistoryWithoutMetadataStillRestores() {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());
        prepareSettings("meo:legacy-history");

        AgentClient client;
        QSignalSpy resetSpy(&client, &AgentClient::resetChat);
        QSignalSpy messageSpy(&client, &AgentClient::message);
        QSignalSpy metadataSpy(&client, &AgentClient::conversationMetadata);

        QTRY_VERIFY(server.hasPendingConnections());
        auto socket = server.nextPendingConnection();
        readRequest(socket);
        replyJson(socket, 200, "OK",
                  "{\"conversation_id\":\"meo:legacy-history\",\"messages\":["
                  "{\"role\":\"user\",\"text\":\"old service\"},"
                  "{\"role\":\"assistant\",\"text\":\"still works\"}]}" );

        QTRY_COMPARE(resetSpy.count(), 1);
        QTRY_COMPARE(messageSpy.count(), 2);
        QCOMPARE(metadataSpy.count(), 0);
        QCOMPARE(messageSpy.at(0).at(1).toString(), QString("old service"));
        QCOMPARE(messageSpy.at(1).at(1).toString(), QString("still works"));
        QTRY_COMPARE(client.status(), QString("Ready"));
        socket->deleteLater();
    }

    void missingSavedConversationClearsStaleIdentity() {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());
        prepareSettings("meo:gone");

        AgentClient client;
        QSignalSpy resetSpy(&client, &AgentClient::resetChat);

        QTRY_VERIFY(server.hasPendingConnections());
        auto socket = server.nextPendingConnection();
        readRequest(socket);
        replyJson(socket, 404, "Not Found", "{\"error\":\"unknown conversation_id\"}");

        QTRY_COMPARE(resetSpy.count(), 1);
        QTRY_VERIFY(!QSettings().contains("serviceConversationId"));
        QVERIFY(client.status().contains("no longer exists"));
        socket->deleteLater();
    }
};

QTEST_GUILESS_MAIN(HistoryRestoreTest)
#include "history-restore-test.moc"

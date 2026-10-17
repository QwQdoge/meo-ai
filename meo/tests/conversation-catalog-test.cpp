#include "agentclient.h"

#include <QSettings>
#include <QSignalSpy>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTest>

class ConversationCatalogTest : public QObject {
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

private slots:
    void initTestCase() {
        QCoreApplication::setOrganizationName("MeoArchConversationCatalogTest");
        QCoreApplication::setApplicationName("MeoAIConversationCatalogTest");
    }

    void cleanup() {
        QSettings().clear();
        qunsetenv("MEO_AI_SERVICE_ENDPOINT");
        qunsetenv("MEO_AI_ENDPOINT");
    }

    void listsSafeMetadataAndRestoresSelectedConversation() {
        QSettings().clear();
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());

        AgentClient client;
        client.refreshConversations();

        QTRY_VERIFY(server.hasPendingConnections());
        auto catalogSocket = server.nextPendingConnection();
        const QByteArray catalogRequest = readRequest(catalogSocket);
        QVERIFY(catalogRequest.contains("GET /v1/conversations "));
        replyJson(catalogSocket, 200, "OK",
                  "{\"conversations\":[{"
                  "\"id\":\"meo:first\","
                  "\"legacy_chat_id\":41,"
                  "\"title\":\"Project Review\","
                  "\"summary\":\"Reviewed the product gaps and next steps.\","
                  "\"title_is_default\":false,"
                  "\"title_is_automatic\":false}]}" );

        QTRY_COMPARE(client.conversations().size(), 1);
        const QVariantMap catalogItem = client.conversations().constFirst().toMap();
        QCOMPARE(catalogItem.value("id").toString(), QString("meo:first"));
        QCOMPARE(catalogItem.value("conversation_id").toString(), QString("meo:first"));
        QCOMPARE(catalogItem.value("title").toString(), QString("Project Review"));
        QCOMPARE(catalogItem.value("summary").toString(),
                 QString("Reviewed the product gaps and next steps."));
        QVERIFY(!catalogItem.contains("legacy_chat_id"));
        catalogSocket->deleteLater();

        QSignalSpy resetSpy(&client, &AgentClient::resetChat);
        QSignalSpy messageSpy(&client, &AgentClient::message);
        QSignalSpy metadataSpy(&client, &AgentClient::conversationMetadata);
        client.resumeConversation("meo:first");

        QTRY_VERIFY(server.hasPendingConnections());
        auto historySocket = server.nextPendingConnection();
        const QByteArray historyRequest = readRequest(historySocket);
        QVERIFY(historyRequest.contains("GET /v1/conversations/meo:first/messages"));
        replyJson(historySocket, 200, "OK",
                  "{\"conversation_id\":\"meo:first\",\"messages\":["
                  "{\"role\":\"user\",\"text\":\"hello\"},"
                  "{\"role\":\"assistant\",\"text\":\"Welcome back\"}]}" );

        QTRY_COMPARE(resetSpy.count(), 1);
        QTRY_COMPARE(messageSpy.count(), 2);
        QTRY_COMPARE(metadataSpy.count(), 1);
        QCOMPARE(client.conversationId(), QString("meo:first"));
        QCOMPARE(QSettings().value("serviceConversationId").toString(), QString("meo:first"));
        QCOMPARE(messageSpy.at(0).at(0).toString(), QString("user"));
        QCOMPARE(messageSpy.at(0).at(1).toString(), QString("hello"));
        QCOMPARE(messageSpy.at(1).at(0).toString(), QString("assistant"));
        QCOMPARE(messageSpy.at(1).at(1).toString(), QString("Welcome back"));
        const QVariantMap metadata = metadataSpy.at(0).at(0).toMap();
        QCOMPARE(metadata.value("conversation_id").toString(), QString("meo:first"));
        QCOMPARE(metadata.value("title").toString(), QString("Project Review"));
        QCOMPARE(metadata.value("summary").toString(),
                 QString("Reviewed the product gaps and next steps."));
        QTRY_COMPARE(client.status(), QString("Ready"));
        historySocket->deleteLater();
    }

    void searchesPersistedMessageHistoryAndCanOpenResult() {
        QSettings().clear();
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());

        AgentClient client;
        client.searchConversations("migration causes");
        QTRY_VERIFY(server.hasPendingConnections());
        auto searchSocket = server.nextPendingConnection();
        const QByteArray request = readRequest(searchSocket);
        QVERIFY(request.contains("GET /v1/conversations/search?q=migration%20causes ")
                || request.contains("GET /v1/conversations/search?q=migration+causes "));
        replyJson(searchSocket, 200, "OK",
                  "{\"query\":\"migration causes\",\"results\":[{"
                  "\"id\":\"meo:history\","
                  "\"title\":\"Migration notes\","
                  "\"summary\":\"School research\","
                  "\"excerpt\":\"…migration causes and consequences…\","
                  "\"message_count\":12,"
                  "\"legacy_chat_id\":77}]}" );
        QTRY_VERIFY(!client.conversationSearchBusy());
        QTRY_COMPARE(client.conversationSearchResults().size(), 1);
        const QVariantMap item = client.conversationSearchResults().constFirst().toMap();
        QCOMPARE(item.value("id").toString(), QString("meo:history"));
        QCOMPARE(item.value("title").toString(), QString("Migration notes"));
        QCOMPARE(item.value("excerpt").toString(), QString("…migration causes and consequences…"));
        QCOMPARE(item.value("message_count").toInt(), 12);
        QVERIFY(!item.contains("legacy_chat_id"));
        searchSocket->deleteLater();

        client.resumeConversation("meo:history");
        QTRY_VERIFY(server.hasPendingConnections());
        auto historySocket = server.nextPendingConnection();
        QVERIFY(readRequest(historySocket).contains("GET /v1/conversations/meo:history/messages"));
        replyJson(historySocket, 200, "OK",
                  "{\"conversation_id\":\"meo:history\",\"messages\":["
                  "{\"role\":\"user\",\"text\":\"migration causes\"}]}" );
        QTRY_COMPARE(client.conversationId(), QString("meo:history"));
        historySocket->deleteLater();

        client.searchConversations("");
        QCOMPARE(client.conversationSearchResults().size(), 0);
    }

    void renamesAndDeletesCurrentConversationWithFallback() {
        QSettings().clear();
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());

        AgentClient client;
        client.refreshConversations();
        QTRY_VERIFY(server.hasPendingConnections());
        auto catalogSocket = server.nextPendingConnection();
        QVERIFY(readRequest(catalogSocket).contains("GET /v1/conversations "));
        replyJson(catalogSocket, 200, "OK",
                  "{\"conversations\":["
                  "{\"id\":\"meo:first\",\"title\":\"First\"},"
                  "{\"id\":\"meo:second\",\"title\":\"Second\"}]}" );
        QTRY_COMPARE(client.conversations().size(), 2);
        catalogSocket->deleteLater();

        client.renameConversation("meo:first", "  Renamed   chat  ");
        QTRY_VERIFY(server.hasPendingConnections());
        auto renameSocket = server.nextPendingConnection();
        const QByteArray renameRequest = readRequest(renameSocket);
        QVERIFY(renameRequest.contains("POST /v1/conversations/meo:first/title "));
        replyJson(renameSocket, 200, "OK",
                  "{\"accepted\":true,\"conversation_id\":\"meo:first\",\"title\":\"Renamed chat\"}");
        QTRY_COMPARE(client.conversations().constFirst().toMap().value("title").toString(),
                     QString("Renamed chat"));
        renameSocket->deleteLater();

        client.resumeConversation("meo:first");
        QTRY_VERIFY(server.hasPendingConnections());
        auto firstHistorySocket = server.nextPendingConnection();
        QVERIFY(readRequest(firstHistorySocket).contains("GET /v1/conversations/meo:first/messages"));
        replyJson(firstHistorySocket, 200, "OK",
                  "{\"conversation_id\":\"meo:first\",\"messages\":["
                  "{\"role\":\"user\",\"text\":\"first history\"}]}" );
        QTRY_COMPARE(client.conversationId(), QString("meo:first"));
        firstHistorySocket->deleteLater();

        QSignalSpy resetSpy(&client, &AgentClient::resetChat);
        const int resetsBeforeDelete = resetSpy.count();
        client.deleteConversation("meo:first");
        QTRY_VERIFY(server.hasPendingConnections());
        auto deleteSocket = server.nextPendingConnection();
        QVERIFY(readRequest(deleteSocket).contains("DELETE /v1/conversations/meo:first "));
        replyJson(deleteSocket, 200, "OK",
                  "{\"accepted\":true,\"conversation_id\":\"meo:first\",\"deleted\":true}");
        deleteSocket->deleteLater();

        QTRY_VERIFY(server.hasPendingConnections());
        auto fallbackSocket = server.nextPendingConnection();
        QVERIFY(readRequest(fallbackSocket).contains("GET /v1/conversations/meo:second/messages"));
        replyJson(fallbackSocket, 200, "OK",
                  "{\"conversation_id\":\"meo:second\",\"messages\":["
                  "{\"role\":\"assistant\",\"text\":\"second history\"}]}" );

        QTRY_COMPARE(client.conversations().size(), 1);
        QTRY_COMPARE(client.conversationId(), QString("meo:second"));
        QCOMPARE(client.conversations().constFirst().toMap().value("id").toString(), QString("meo:second"));
        QVERIFY(resetSpy.count() >= resetsBeforeDelete + 2);
        QCOMPARE(QSettings().value("serviceConversationId").toString(), QString("meo:second"));
        QTRY_COMPARE(client.status(), QString("Ready"));
        fallbackSocket->deleteLater();
    }
};

QTEST_GUILESS_MAIN(ConversationCatalogTest)
#include "conversation-catalog-test.moc"
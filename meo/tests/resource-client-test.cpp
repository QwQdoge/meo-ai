#include "agentclient.h"
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSettings>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
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

    static QByteArray requestBody(const QByteArray &request) {
        const int split = request.indexOf("\r\n\r\n");
        return split < 0 ? QByteArray() : request.mid(split + 4);
    }

    static void replyJson(QTcpSocket *socket, int status, const QByteArray &body) {
        QByteArray statusText;
        switch (status) {
        case 200: statusText = "200 OK"; break;
        case 201: statusText = "201 Created"; break;
        case 404: statusText = "404 Not Found"; break;
        case 503: statusText = "503 Service Unavailable"; break;
        default: statusText = QByteArray::number(status) + " Error"; break;
        }
        socket->write("HTTP/1.1 " + statusText
                      + "\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                      + QByteArray::number(body.size()) + "\r\n\r\n" + body);
        socket->flush();
        socket->disconnectFromHost();
    }

    static void writeFile(const QString &path, const QByteArray &content) {
        QFile file(path);
        QVERIFY(file.open(QIODevice::WriteOnly));
        QCOMPARE(file.write(content), content.size());
        file.close();
    }

    static void createConversation(QTcpServer &server, const QByteArray &conversationId) {
        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *socket = server.nextPendingConnection();
        const QByteArray request = readRequest(socket);
        QVERIFY(request.startsWith("POST /v1/conversations "));
        replyJson(socket, 201, "{\"conversation_id\":\"" + conversationId + "\"}");
        socket->deleteLater();
    }

    static void createLongText(
        AgentClient &client,
        QTcpServer &server,
        const QByteArray &conversationId,
        const QByteArray &resourceId,
        const QString &name = QStringLiteral("research.txt")
    ) {
        client.addLongTextResource(name, QStringLiteral("alpha beta gamma"));
        createConversation(server, conversationId);

        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *resource = server.nextPendingConnection();
        const QByteArray request = readRequest(resource);
        QVERIFY(request.contains("POST /v1/conversations/" + conversationId + "/resources/text"));
        replyJson(
            resource,
            201,
            "{\"conversation_id\":\"" + conversationId
                + "\",\"resource\":{\"resource_id\":\"" + resourceId
                + "\",\"kind\":\"long_text\",\"name\":\"" + name.toUtf8()
                + "\",\"mime_type\":\"text/plain; charset=utf-8\",\"size_bytes\":16,"
                  "\"sha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\","
                  "\"state\":\"ready\"}}");
        resource->deleteLater();
        QTRY_COMPARE(client.pendingResources().size(), 1);
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
        QTcpSocket *createConversationSocket = server.nextPendingConnection();
        const QByteArray conversationRequest = readRequest(createConversationSocket);
        QVERIFY(conversationRequest.startsWith("POST /v1/conversations "));
        replyJson(createConversationSocket, 201, "{\"conversation_id\":\"meo:resources\"}");

        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *createResource = server.nextPendingConnection();
        const QByteArray resourceRequest = readRequest(createResource);
        QVERIFY(resourceRequest.contains("POST /v1/conversations/meo:resources/resources/text"));
        const auto resourceBody = QJsonDocument::fromJson(requestBody(resourceRequest)).object();
        QCOMPARE(resourceBody.value("name").toString(), QString("research.txt"));
        QCOMPARE(resourceBody.value("text").toString(), QString("alpha beta gamma"));
        replyJson(
            createResource,
            201,
            "{\"conversation_id\":\"meo:resources\",\"resource\":{\"resource_id\":\"resource:0123456789abcdef0123456789abcdef\",\"kind\":\"long_text\",\"name\":\"research.txt\",\"mime_type\":\"text/plain; charset=utf-8\",\"size_bytes\":16,\"sha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"state\":\"ready\"}}");

        QTRY_COMPARE(client.pendingResources().size(), 1);
        QCOMPARE(client.pendingResources().at(0).toMap().value("name").toString(), QString("research.txt"));

        // The regular composer entry point must automatically include pending resources.
        client.send("Use the attached notes");
        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *message = server.nextPendingConnection();
        const QByteArray messageRequest = readRequest(message);
        QVERIFY(messageRequest.contains("POST /v1/conversations/meo:resources/messages"));
        const auto messageBody = QJsonDocument::fromJson(requestBody(messageRequest)).object();
        QCOMPARE(messageBody.value("text").toString(), QString("Use the attached notes"));
        const auto ids = messageBody.value("resource_ids").toArray();
        QCOMPARE(ids.size(), 1);
        QCOMPARE(ids.at(0).toString(), QString("resource:0123456789abcdef0123456789abcdef"));
        // Do not consume the attachment merely because the local POST started.
        QCOMPARE(client.pendingResources().size(), 1);

        message->write("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\nX-Meo-Request-Id: req-resource\r\n\r\n");
        message->flush();
        QTRY_COMPARE(client.pendingResources().size(), 0);
        message->write("data: {\"seq\":1,\"type\":\"request.started\",\"request_id\":\"req-resource\",\"conversation_id\":\"meo:resources\",\"state\":\"running_model\"}\n\n");
        message->write("data: {\"seq\":2,\"type\":\"request.completed\",\"request_id\":\"req-resource\",\"state\":\"completed\"}\n\n");
        message->flush();
        message->disconnectFromHost();
        QTRY_VERIFY(!client.busy());
        QVERIFY(client.status().contains("Ready"));

        createConversationSocket->deleteLater();
        createResource->deleteLater();
        message->deleteLater();
    }

    void multipleSelectedFilesAreQueuedAndUploaded() {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());
        QSettings().clear();
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString alphaPath = directory.filePath("alpha.txt");
        const QString betaPath = directory.filePath("beta.txt");
        writeFile(alphaPath, "alpha");
        writeFile(betaPath, "beta-two");

        AgentClient client;
        // Mirrors LongPastePanel's OpenFiles loop: both calls happen before the
        // first reserve request can finish.
        client.addFileResource(QUrl::fromLocalFile(alphaPath));
        client.addFileResource(QUrl::fromLocalFile(betaPath));
        createConversation(server, "meo:multi");

        const QByteArray resourceOne = "resource:11111111111111111111111111111111";
        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *reserveOne = server.nextPendingConnection();
        const QByteArray reserveOneRequest = readRequest(reserveOne);
        QVERIFY(reserveOneRequest.contains("POST /v1/conversations/meo:multi/resources"));
        const auto reserveOneBody = QJsonDocument::fromJson(requestBody(reserveOneRequest)).object();
        QCOMPARE(reserveOneBody.value("name").toString(), QString("alpha.txt"));
        QCOMPARE(reserveOneBody.value("size_bytes").toInt(), 5);
        replyJson(reserveOne, 201,
                  "{\"resource\":{\"resource_id\":\"" + resourceOne
                      + "\",\"state\":\"uploading\"}}");

        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *uploadOne = server.nextPendingConnection();
        const QByteArray uploadOneRequest = readRequest(uploadOne);
        QVERIFY(uploadOneRequest.contains("PUT /v1/conversations/meo:multi/resources/" + resourceOne + "/content"));
        QCOMPARE(requestBody(uploadOneRequest), QByteArray("alpha"));
        replyJson(uploadOne, 200,
                  "{\"resource\":{\"resource_id\":\"" + resourceOne
                      + "\",\"kind\":\"attachment\",\"name\":\"alpha.txt\","
                        "\"mime_type\":\"text/plain\",\"size_bytes\":5,"
                        "\"sha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\","
                        "\"state\":\"ready\"}}");

        const QByteArray resourceTwo = "resource:22222222222222222222222222222222";
        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *reserveTwo = server.nextPendingConnection();
        const QByteArray reserveTwoRequest = readRequest(reserveTwo);
        QVERIFY(reserveTwoRequest.contains("POST /v1/conversations/meo:multi/resources"));
        const auto reserveTwoBody = QJsonDocument::fromJson(requestBody(reserveTwoRequest)).object();
        QCOMPARE(reserveTwoBody.value("name").toString(), QString("beta.txt"));
        QCOMPARE(reserveTwoBody.value("size_bytes").toInt(), 8);
        replyJson(reserveTwo, 201,
                  "{\"resource\":{\"resource_id\":\"" + resourceTwo
                      + "\",\"state\":\"uploading\"}}");

        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *uploadTwo = server.nextPendingConnection();
        const QByteArray uploadTwoRequest = readRequest(uploadTwo);
        QVERIFY(uploadTwoRequest.contains("PUT /v1/conversations/meo:multi/resources/" + resourceTwo + "/content"));
        QCOMPARE(requestBody(uploadTwoRequest), QByteArray("beta-two"));
        replyJson(uploadTwo, 200,
                  "{\"resource\":{\"resource_id\":\"" + resourceTwo
                      + "\",\"kind\":\"attachment\",\"name\":\"beta.txt\","
                        "\"mime_type\":\"text/plain\",\"size_bytes\":8,"
                        "\"sha256\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\","
                        "\"state\":\"ready\"}}");

        QTRY_COMPARE(client.pendingResources().size(), 2);
        QCOMPARE(client.pendingResources().at(0).toMap().value("name").toString(), QString("alpha.txt"));
        QCOMPARE(client.pendingResources().at(1).toMap().value("name").toString(), QString("beta.txt"));
        QTRY_VERIFY(!client.actionBusy());

        reserveOne->deleteLater();
        uploadOne->deleteLater();
        reserveTwo->deleteLater();
        uploadTwo->deleteLater();
    }

    void failedMessageKeepsPendingResourceForRetry() {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());
        QSettings().clear();

        AgentClient client;
        const QByteArray resourceId = "resource:33333333333333333333333333333333";
        createLongText(client, server, "meo:retry", resourceId);

        client.send("Please use this attachment");
        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *message = server.nextPendingConnection();
        const QByteArray request = readRequest(message);
        QVERIFY(request.contains("POST /v1/conversations/meo:retry/messages"));
        QCOMPARE(client.pendingResources().size(), 1);
        replyJson(message, 503, "{\"error\":\"temporarily unavailable\"}");

        QTRY_VERIFY(!client.busy());
        QTRY_VERIFY(client.requestFailed());
        QTRY_VERIFY(client.requestRetryable());
        QCOMPARE(client.pendingResources().size(), 1);
        QCOMPARE(client.pendingResources().at(0).toMap().value("resource_id").toString(),
                 QString::fromUtf8(resourceId));
        message->deleteLater();

        client.retryLastRequest();
        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *retry = server.nextPendingConnection();
        const QByteArray retryRequest = readRequest(retry);
        QVERIFY(retryRequest.contains("POST /v1/conversations/meo:retry/messages"));
        const auto retryBody = QJsonDocument::fromJson(requestBody(retryRequest)).object();
        QCOMPARE(retryBody.value("text").toString(), QString("Please use this attachment"));
        const auto retryIds = retryBody.value("resource_ids").toArray();
        QCOMPARE(retryIds.size(), 1);
        QCOMPARE(retryIds.at(0).toString(), QString::fromUtf8(resourceId));
        QCOMPARE(client.pendingResources().size(), 1);

        retry->write("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\n"
                     "X-Meo-Request-Id: req-resource-retry\r\n\r\n");
        retry->flush();
        QTRY_COMPARE(client.pendingResources().size(), 0);
        retry->write("data: {\"seq\":1,\"type\":\"request.started\","
                     "\"request_id\":\"req-resource-retry\",\"conversation_id\":\"meo:retry\","
                     "\"state\":\"running_model\"}\n\n");
        retry->write("data: {\"seq\":2,\"type\":\"request.completed\","
                     "\"request_id\":\"req-resource-retry\",\"state\":\"completed\"}\n\n");
        retry->flush();
        retry->disconnectFromHost();
        QTRY_VERIFY(!client.busy());
        QTRY_VERIFY(!client.requestFailed());
        QVERIFY(client.status().contains("Ready"));
        retry->deleteLater();
    }

    void clearPendingResourcesDeletesBackingResources() {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());
        QSettings().clear();

        AgentClient client;
        const QByteArray resourceId = "resource:44444444444444444444444444444444";
        createLongText(client, server, "meo:clear", resourceId, QStringLiteral("clear-me.txt"));

        client.clearPendingResources();
        QTRY_VERIFY(server.hasPendingConnections());
        QTcpSocket *remove = server.nextPendingConnection();
        const QByteArray request = readRequest(remove);
        QVERIFY(request.contains("DELETE /v1/conversations/meo:clear/resources/" + resourceId));
        QCOMPARE(client.pendingResources().size(), 1);
        replyJson(remove, 200,
                  "{\"conversation_id\":\"meo:clear\",\"resource_id\":\"" + resourceId
                      + "\",\"deleted\":true}");

        QTRY_COMPARE(client.pendingResources().size(), 0);
        QTRY_VERIFY(!client.actionBusy());
        QVERIFY(client.status().contains("cleared"));
        remove->deleteLater();
    }
};

QTEST_GUILESS_MAIN(ResourceClientTest)
#include "resource-client-test.moc"
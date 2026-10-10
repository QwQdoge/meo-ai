#include "agentclient.h"
#include <QSettings>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTest>

class ServiceMetadataTest : public QObject {
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

    static void replyJson(QTcpSocket *socket, const QByteArray &body) {
        socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                      + QByteArray::number(body.size()) + "\r\n\r\n" + body);
        socket->flush();
        socket->disconnectFromHost();
    }

private slots:
    void initTestCase() {
        QCoreApplication::setOrganizationName("MeoArchMetadataTest");
        QCoreApplication::setApplicationName("MeoAIMetadataTest");
    }

    void cleanup() {
        QSettings().clear();
        qunsetenv("MEO_AI_SERVICE_ENDPOINT");
        qunsetenv("MEO_AI_ENDPOINT");
    }

    void refreshesStructuredServiceMetadata() {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        qputenv("MEO_AI_SERVICE_ENDPOINT",
                QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());
        QSettings().clear();

        AgentClient client;
        QVERIFY(client.serviceMode());
        QVERIFY(client.models().isEmpty());
        QVERIFY(client.modelRoles().isEmpty());
        QVERIFY(client.controls().isEmpty());
        QVERIFY(client.memoryState().isEmpty());
        QVERIFY(client.memories().isEmpty());
        client.refreshServiceMetadata();

        struct Exchange { QByteArray path; QByteArray body; };
        const QList<Exchange> exchanges{
            {"GET /v1/agent-state ", "{\"ready\":true,\"active_requests\":0,\"request_states\":{\"running_model\":0}}"},
            {"GET /v1/models ", "{\"models\":[{\"model_id\":\"local:tiny\",\"label\":\"Tiny\",\"provider\":\"Local\",\"selection_scope\":\"profile\",\"selected\":true}]}"},
            {"GET /v1/model-roles ", "{\"model_roles\":[{\"role_id\":\"title\",\"label\":\"Title\",\"description\":\"Chat titles\",\"workload\":\"auxiliary\",\"preferred_model_id\":\"local:tiny\",\"preferred_available\":true,\"fallback_model_id\":\"local:tiny\",\"runtime_supported\":false,\"routing_status\":\"preference_only\",\"selection_scope\":\"profile\"}]}"},
            {"GET /v1/skills ", "{\"skills\":[{\"skill_id\":\"diagnostics\",\"label\":\"Diagnostics\",\"enabled\":true,\"configured_enabled\":true,\"selection_scope\":\"profile\",\"override_source\":\"\"}]}"},
            {"GET /v1/mcp-servers ", "{\"mcp_servers\":[{\"server_id\":\"mcp:files\",\"label\":\"Files\",\"enabled\":false}]}"},
            {"GET /v1/controls ", "{\"controls\":[{\"control_id\":\"memory.enabled\",\"label\":\"Memory\",\"kind\":\"toggle\",\"value\":true,\"scope\":\"profile\",\"writable\":true,\"restart_required\":false}]}"},
            {"GET /v1/memory ", "{\"supported\":true,\"enabled\":true,\"scope\":null,\"query\":\"\",\"memories\":[{\"memory_id\":\"memory:one\",\"text\":\"Compact native UI\",\"scope\":\"account\",\"source\":\"test\",\"created_at\":\"2026-10-10T00:00:00Z\",\"updated_at\":\"2026-10-10T00:00:00Z\",\"state\":\"active\",\"pinned\":true,\"sync_state\":\"local\",\"workspace_id\":\"\",\"conversation_id\":\"\"}]}"},
        };

        for (const auto &exchange : exchanges) {
            QTRY_VERIFY(server.hasPendingConnections());
            QTcpSocket *socket = server.nextPendingConnection();
            const QByteArray request = readRequest(socket);
            QVERIFY2(request.contains(exchange.path), request.constData());
            replyJson(socket, exchange.body);
            socket->deleteLater();
        }

        QTRY_VERIFY(!client.metadataBusy());
        QCOMPARE(client.metadataStatus(), QString("Ready"));
        QCOMPARE(client.agentState().value("ready").toBool(), true);
        QCOMPARE(client.agentState().value("active_requests").toInt(), 0);
        QCOMPARE(client.models().size(), 1);
        QCOMPARE(client.models().at(0).toMap().value("model_id").toString(), QString("local:tiny"));
        QCOMPARE(client.models().at(0).toMap().value("selected").toBool(), true);
        QCOMPARE(client.modelRoles().size(), 1);
        QCOMPARE(client.modelRoles().at(0).toMap().value("role_id").toString(), QString("title"));
        QCOMPARE(client.modelRoles().at(0).toMap().value("preferred_model_id").toString(), QString("local:tiny"));
        QCOMPARE(client.skills().size(), 1);
        QCOMPARE(client.skills().at(0).toMap().value("skill_id").toString(), QString("diagnostics"));
        QCOMPARE(client.mcpServers().size(), 1);
        QCOMPARE(client.mcpServers().at(0).toMap().value("server_id").toString(), QString("mcp:files"));
        QCOMPARE(client.controls().size(), 1);
        QCOMPARE(client.controls().at(0).toMap().value("control_id").toString(), QString("memory.enabled"));
        QCOMPARE(client.controls().at(0).toMap().value("value").toBool(), true);
        QCOMPARE(client.memoryState().value("supported").toBool(), true);
        QCOMPARE(client.memoryState().value("enabled").toBool(), true);
        QCOMPARE(client.memories().size(), 1);
        QCOMPARE(client.memories().at(0).toMap().value("memory_id").toString(), QString("memory:one"));
        QCOMPARE(client.memories().at(0).toMap().value("pinned").toBool(), true);
    }
};

QTEST_GUILESS_MAIN(ServiceMetadataTest)
#include "service-metadata-test.moc"

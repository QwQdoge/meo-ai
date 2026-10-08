#pragma once
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QObject>
#include <QVariantList>

class AgentClient : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(QString status READ status NOTIFY changed)
    Q_PROPERTY(QVariantList options READ options NOTIFY changed)
public:
    explicit AgentClient(QObject *parent = nullptr);
    bool busy() const { return m_reply != nullptr; }
    QString status() const { return m_status; }
    QVariantList options() const { return m_options; }
    Q_INVOKABLE void send(const QString &text);
    Q_INVOKABLE void choose(int index);
    Q_INVOKABLE void newChat();
signals:
    void changed();
    void message(const QString &role, const QString &text);
    void delta(const QString &text);
    void toolEvent(const QVariantMap &event);
    void resetChat();
private:
    void request(const QString &text);
    void consume();
    QNetworkAccessManager m_network;
    QNetworkReply *m_reply = nullptr;
    QByteArray m_buffer;
    QString m_user;
    QString m_status;
    QVariantList m_options;
    bool m_done = false;
};

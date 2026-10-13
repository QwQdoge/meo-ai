#pragma once

#include "agentclient.h"

class NativeAgentClient final : public AgentClient {
public:
    explicit NativeAgentClient(QObject *parent = nullptr) : AgentClient(parent) {
        connect(this, &AgentClient::changed, this, [this] {
            if (!m_newChatPending || busy() || actionBusy() || resourceCleanupBusy()) return;

            // Resource deletion is best-effort. Even if AgentService could not
            // delete one backing object, its conversation-scoped identity must
            // never survive into the next chat as a visible/reusable chip.
            m_newChatPending = false;
            if (!pendingResources().isEmpty())
                abandonPendingResources();
            AgentClient::newChat();
        });
    }

    void send(const QString &text) override {
        AgentClient::send(text);
    }

    void newChat() override {
        if (busy() || actionBusy() || !options().isEmpty()) return;
        if (pendingResources().isEmpty()) {
            AgentClient::newChat();
            return;
        }

        m_newChatPending = true;
        clearPendingResources();
    }

private:
    bool m_newChatPending = false;
};

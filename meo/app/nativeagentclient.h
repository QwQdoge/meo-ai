#pragma once

#include "agentclient.h"

class NativeAgentClient final : public AgentClient {
public:
    using AgentClient::AgentClient;

    void send(const QString &text) override {
        sendWithPendingResources(text);
    }
};

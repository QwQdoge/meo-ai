export type MeoAgentRequest = {
  conversationId: string;
  text: string;
  projectId?: string;
};

export type MeoAgentEvent = {
  event: string;
  id?: number;
  data: Record<string, unknown>;
};

export type MeoCapabilityKind = "skill" | "connector";
export type MeoCapabilityOrigin = "builtin" | "official" | "mcp" | "plugin" | "system";
export type MeoCapabilityConnectionState = "not_required" | "disconnected" | "connected" | "error";
export type MeoCapabilityEffect = "read" | "write" | "execute";

export type MeoCapabilityPermission = {
  permission_id: string;
  label: string;
  effect: MeoCapabilityEffect;
  sensitive?: boolean;
};

export type MeoCapabilityTool = {
  tool_id: string;
  label: string;
  description?: string;
  effect: MeoCapabilityEffect;
  confirmation_required?: boolean;
  input_schema?: Record<string, unknown>;
};

export type MeoCapability = {
  capability_id: string;
  kind: MeoCapabilityKind;
  label: string;
  description?: string;
  origin: MeoCapabilityOrigin;
  provider?: string;
  icon?: string;
  enabled: boolean;
  configurable: boolean;
  connection_state: MeoCapabilityConnectionState;
  permissions?: MeoCapabilityPermission[];
  tools?: MeoCapabilityTool[];
  requires?: string[];
  context_hint?: string;
  tags?: string[];
};

export type MeoAgentClientConfig = {
  cloudBaseUrl: string;
  eventsUrl: string;
  getAccessToken: () => Promise<string>;
};

export class MeoAgentClient {
  private readonly cloudBaseUrl: string;
  private readonly eventsUrl: string;
  private readonly getAccessToken: () => Promise<string>;

  constructor(config: MeoAgentClientConfig) {
    this.cloudBaseUrl = httpsUrl(config.cloudBaseUrl, "cloudBaseUrl");
    this.eventsUrl = httpsUrl(config.eventsUrl, "eventsUrl");
    this.getAccessToken = config.getAccessToken;
  }

  async listCapabilities(): Promise<MeoCapability[]> {
    const response = await this.authorizedFetch(`${this.cloudBaseUrl}/v1/capabilities`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    const value = await jsonObject(response);
    const capabilities = value.capabilities;
    if (!Array.isArray(capabilities)) throw new Error("Meo Cloud did not return capabilities");
    return capabilities.map(parseCapability);
  }

  async setCapabilityEnabled(capabilityId: string, enabled: boolean): Promise<MeoCapability> {
    const id = capabilityId.trim();
    if (!validCapabilityId(id)) throw new Error("Invalid capability identifier");
    const response = await this.authorizedFetch(
      `${this.cloudBaseUrl}/v1/capabilities/${encodeURIComponent(id)}/state`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      },
    );
    const value = await jsonObject(response);
    return parseCapability(value.capability);
  }

  async createRun(request: MeoAgentRequest): Promise<{ runId: string }> {
    const text = request.text.trim();
    const conversationId = request.conversationId.trim();
    if (!text || !conversationId) throw new Error("conversationId and text are required");

    // Intentionally no device_id, workspace_ref, command, shell, scopes, or
    // Full Access fields exist in this public web contract. Routing and policy
    // stay server-owned.
    const body: Record<string, string> = {
      conversation_id: conversationId,
      text,
    };
    if (request.projectId?.trim()) body.project_id = request.projectId.trim();

    const response = await this.authorizedFetch(`${this.cloudBaseUrl}/v1/agent-runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const value = await jsonObject(response);
    const runId = value.run_id;
    if (typeof runId !== "string" || !runId) throw new Error("Meo Cloud did not return run_id");
    return { runId };
  }

  async cancelRun(runId: string): Promise<void> {
    await this.authorizedFetch(
      `${this.cloudBaseUrl}/v1/agent-runs/${encodeURIComponent(runId)}/cancel`,
      { method: "POST" },
    );
  }

  async decide(runId: string, decisionId: string, optionIndex: number): Promise<void> {
    if (!Number.isSafeInteger(optionIndex) || optionIndex < 0) {
      throw new Error("optionIndex must be a non-negative integer");
    }
    await this.authorizedFetch(
      `${this.cloudBaseUrl}/v1/agent-runs/${encodeURIComponent(runId)}/decisions/${encodeURIComponent(decisionId)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ option_index: optionIndex }),
      },
    );
  }

  async *events(runId: string, after = -1): AsyncGenerator<MeoAgentEvent> {
    if (!Number.isSafeInteger(after) || after < -1) throw new Error("after must be >= -1");
    const url = new URL(this.eventsUrl);
    url.searchParams.set("run_id", runId);
    url.searchParams.set("after", String(after));
    const response = await this.authorizedFetch(url.toString(), {
      method: "GET",
      headers: { Accept: "text/event-stream" },
    });
    if (!response.body) throw new Error("Meo Agent event stream has no body");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
        let boundary = buffer.indexOf("\n\n");
        while (boundary >= 0) {
          const block = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          const parsed = parseSseBlock(block);
          if (parsed?.event === "error") throw new Error("Meo Agent event stream could not be resumed safely");
          if (parsed) yield parsed;
          boundary = buffer.indexOf("\n\n");
        }
        if (done) break;
      }
    } finally {
      try {
        await reader.cancel();
      } finally {
        reader.releaseLock();
      }
    }
  }

  private async authorizedFetch(url: string, init: RequestInit): Promise<Response> {
    const token = (await this.getAccessToken()).trim();
    if (!token) throw new Error("Meo Account session is unavailable");
    const headers = new Headers(init.headers ?? {});
    headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(url, { ...init, headers, credentials: "omit" });
    if (response.ok) return response;
    let message = `Meo Cloud returned HTTP ${response.status}`;
    try {
      const value = await response.json();
      if (typeof value?.error?.message === "string") message = value.error.message;
    } catch {
      // Keep the generic message; never surface raw HTML or proxy diagnostics.
    }
    throw new Error(message);
  }
}

function parseCapability(value: unknown): MeoCapability {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Meo capability payload is invalid");
  }
  const item = value as Record<string, unknown>;
  const id = typeof item.capability_id === "string" ? item.capability_id : "";
  const kind = item.kind;
  const origin = item.origin;
  const connection = item.connection_state;
  if (
    !validCapabilityId(id) ||
    (kind !== "skill" && kind !== "connector") ||
    !["builtin", "official", "mcp", "plugin", "system"].includes(String(origin)) ||
    !["not_required", "disconnected", "connected", "error"].includes(String(connection)) ||
    typeof item.label !== "string" ||
    typeof item.enabled !== "boolean" ||
    typeof item.configurable !== "boolean"
  ) {
    throw new Error("Meo capability payload is invalid");
  }
  return item as unknown as MeoCapability;
}

function validCapabilityId(value: string): boolean {
  return /^[A-Za-z0-9._:-]{1,128}$/.test(value);
}

function parseSseBlock(block: string): MeoAgentEvent | null {
  let event = "message";
  let id: number | undefined;
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("id:")) {
      const parsed = Number(line.slice(3).trim());
      if (Number.isSafeInteger(parsed)) id = parsed;
    } else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (!data.length) return null;
  const value = JSON.parse(data.join("\n"));
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Meo Agent event data is invalid");
  }
  return { event, id, data: value as Record<string, unknown> };
}

async function jsonObject(response: Response): Promise<Record<string, unknown>> {
  const value = await response.json();
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Meo Cloud returned invalid JSON");
  }
  return value as Record<string, unknown>;
}

function httpsUrl(value: string, label: string): string {
  const url = new URL(value);
  if (url.protocol !== "https:") {
    const loopback = url.protocol === "http:" && ["127.0.0.1", "localhost", "::1"].includes(url.hostname);
    if (!loopback) throw new Error(`${label} must use https://`);
  }
  return url.toString().replace(/\/$/, "");
}

import { createClient } from "npm:@supabase/supabase-js@2.112.3";

const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
const anonKey = Deno.env.get("SUPABASE_ANON_KEY") ?? "";
const encoder = new TextEncoder();

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    },
  });
}

function uuid(value: string | null) {
  return Boolean(
    value && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value),
  );
}

function sse(event: string, data: unknown, id?: number) {
  return `${id == null ? "" : `id: ${id}\n`}event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

Deno.serve(async (req) => {
  if (req.method !== "GET") return json({ error: "Method not allowed" }, 405);
  if (!supabaseUrl || !anonKey) return json({ error: "Service unavailable" }, 503);

  const authorization = req.headers.get("Authorization") ?? "";
  if (!authorization.startsWith("Bearer ")) {
    return json({ error: "Authentication required" }, 401);
  }

  const url = new URL(req.url);
  const runId = url.searchParams.get("run_id");
  if (!uuid(runId)) return json({ error: "Invalid run_id" }, 400);
  const parsedAfter = Number(url.searchParams.get("after") ?? "-1");
  if (!Number.isSafeInteger(parsedAfter) || parsedAfter < -1) {
    return json({ error: "Invalid after cursor" }, 400);
  }

  const client = createClient(supabaseUrl, anonKey, {
    global: { headers: { Authorization: authorization } },
    auth: { persistSession: false, autoRefreshToken: false },
  });

  const { data: userData, error: userError } = await client.auth.getUser();
  if (userError || !userData.user) return json({ error: "Authentication required" }, 401);

  const { data: run, error: runError } = await client
    .from("ai_agent_runs")
    .select("id,status")
    .eq("id", runId)
    .maybeSingle();
  if (runError) return json({ error: "Unable to read AgentRun" }, 500);
  if (!run) return json({ error: "AgentRun not found" }, 404);

  let cursor = parsedAfter;
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      try {
        controller.enqueue(encoder.encode(sse("ready", { run_id: runId, after: cursor })));
        for (let iteration = 0; iteration < 80; iteration++) {
          const { data, error } = await client
            .from("ai_agent_events")
            .select("seq,event_type,payload,created_at")
            .eq("run_id", runId)
            .gt("seq", cursor)
            .order("seq", { ascending: true })
            .limit(100);

          if (error) {
            controller.enqueue(encoder.encode(sse("stream_error", { code: "event_query_failed" })));
            break;
          }

          let terminal = false;
          for (const row of data ?? []) {
            const seq = Number(row.seq);
            if (!Number.isSafeInteger(seq) || seq <= cursor) continue;
            cursor = seq;
            controller.enqueue(
              encoder.encode(
                sse(
                  String(row.event_type || "event"),
                  { run_id: runId, seq, payload: row.payload, created_at: row.created_at },
                  seq,
                ),
              ),
            );
            if (row.event_type === "done" || row.event_type === "error") terminal = true;
          }

          if (terminal) break;
          await new Promise((resolve) => setTimeout(resolve, 750));
        }
      } catch {
        controller.enqueue(encoder.encode(sse("stream_error", { code: "stream_failed" })));
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-store",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
});

# Meo runner (local execution for Work)

`meo-runner` is the headless device side of Work. Run it on a computer you own, sign in once, and
that computer appears under **Run on** in Work on the web, phone and other desktops. Tasks sent to
it run in the folder you chose with the same tools as the desktop app: read, search, edit, apply
patches, run shell commands and call **local MCP servers**. It only connects out to Meo API
(realtime hub); nothing listens on the network except the one-shot sign-in loopback callback.

```sh
cd meo/core-rs
cargo build --release --bin meo-runner
./target/release/meo-runner --name "Studio Mac" --folder ~/code/project
```

A browser opens for Meo Account sign-in the first time; the session is then kept like the desktop
app's. Stop with Ctrl-C.

## Safety

- Permission levels (Ask / Low / Smart / All) apply as in the desktop app. A local MCP call is a
  command-level action, so every level except *All* asks first; the controller approves or refuses
  from the device that sent the task.
- A command that asks for a password is refused: only a person at that computer could type it.
- Paths stay inside the work folder; destructive commands are denied or need approval.
- MCP servers run as you. Only list servers you trust. Tool output is data, never instructions.

## Local MCP servers

Same file shape as Claude Desktop / Claude Code, in `~/.config/meo/mcp.json` and/or
`<work folder>/.mcp.json` (the folder's file wins by server name):

```json
{ "mcpServers": {
    "fetch":      { "command": "uvx", "args": ["mcp-server-fetch"] },
    "filesystem": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "."] },
    "git":        { "command": "uvx", "args": ["mcp-server-git", "--repository", "."] }
} }
```

These are open-source servers from `modelcontextprotocol/servers`. Servers start on first use and
stay up while the folder is open; the model sees their tools in the Work prompt and calls them with
`{"tool":"mcp","args":{"server":"fetch","name":"fetch","args":{"url":"…"}}}`.

The desktop app uses the same host, so it gets local MCP too. The browser cannot run commands or
stdio servers; it only edits a folder you pick (Open folder) and uses remote MCP through Meo API.

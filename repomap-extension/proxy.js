#!/usr/bin/env node
"use strict";

/**
 * Transparent stdio proxy for the repomap MCP server.
 *
 * Usage:  node proxy.js <command> [args...]
 * Example: node proxy.js python3 -m repomap.server
 *
 * Forwards stdin/stdout byte-for-byte between the parent (Cursor)
 * and the child (repomap MCP server). Scans the stream for JSON-RPC
 * tools/call requests and their responses, writing structured events
 * to ~/.repomap/events.jsonl for the extension to tail-follow.
 */

const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const os = require("os");

const LOG_DIR = path.join(os.homedir(), ".repomap");
const LOG_FILE = path.join(LOG_DIR, "events.jsonl");

if (!fs.existsSync(LOG_DIR)) {
  fs.mkdirSync(LOG_DIR, { recursive: true });
}

const logStream = fs.createWriteStream(LOG_FILE, { flags: "a" });

function logEvent(obj) {
  logStream.write(JSON.stringify(obj) + "\n");
}

// --- Launch child MCP server ---

const childCmd = process.argv[2];
const childArgs = process.argv.slice(3);

if (!childCmd) {
  process.stderr.write("proxy.js: no command specified\n");
  process.exit(1);
}

const child = spawn(childCmd, childArgs, {
  stdio: ["pipe", "pipe", "pipe"],
  env: process.env,
});

// --- Track pending tool calls ---

const pendingCalls = new Map();

// --- Stdin: Cursor -> proxy -> child ---

let inBuf = "";

process.stdin.on("data", (chunk) => {
  child.stdin.write(chunk);

  inBuf += chunk.toString("utf-8");
  const lines = inBuf.split("\n");
  inBuf = lines.pop() || "";
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const msg = JSON.parse(trimmed);
      if (msg.method === "tools/call" && msg.id != null) {
        const toolName = msg.params && msg.params.name;
        const toolArgs = msg.params && msg.params.arguments;
        pendingCalls.set(msg.id, toolName);
        logEvent({
          ts: new Date().toISOString(),
          type: "call",
          id: msg.id,
          tool: toolName || "unknown",
          args: toolArgs || {},
        });
      }
    } catch (_) {
      /* not JSON or not a tool call — ignore */
    }
  }
});

process.stdin.on("end", () => {
  try { child.stdin.end(); } catch (_) { /* ignore */ }
});

// --- Stdout: child -> proxy -> Cursor ---

let outBuf = "";

child.stdout.on("data", (chunk) => {
  process.stdout.write(chunk);

  outBuf += chunk.toString("utf-8");
  const lines = outBuf.split("\n");
  outBuf = lines.pop() || "";
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const msg = JSON.parse(trimmed);
      if (msg.id != null && pendingCalls.has(msg.id)) {
        const toolName = pendingCalls.get(msg.id);
        pendingCalls.delete(msg.id);

        if (msg.error) {
          logEvent({
            ts: new Date().toISOString(),
            type: "error",
            id: msg.id,
            tool: toolName,
            error: msg.error.message || JSON.stringify(msg.error),
          });
        } else {
          const content = msg.result && msg.result.content;
          const text = Array.isArray(content)
            ? content.map((c) => c.text || "").join("\n")
            : "";
          logEvent({
            ts: new Date().toISOString(),
            type: "result",
            id: msg.id,
            tool: toolName,
            text: text,
          });
        }
      }
    } catch (_) {
      /* not JSON — ignore */
    }
  }
});

// --- Stderr: pass through ---

child.stderr.on("data", (chunk) => {
  process.stderr.write(chunk);
});

// --- Lifecycle ---

child.on("exit", (code, signal) => {
  logEvent({ ts: new Date().toISOString(), type: "exit", code, signal });
  logStream.end(() => process.exit(code ?? 1));
});

child.on("error", (err) => {
  logEvent({ ts: new Date().toISOString(), type: "error", id: null, tool: null, error: err.message });
  process.stderr.write("proxy.js: child error: " + err.message + "\n");
  logStream.end(() => process.exit(1));
});

process.on("SIGTERM", () => { child.kill("SIGTERM"); });
process.on("SIGINT", () => { child.kill("SIGINT"); });

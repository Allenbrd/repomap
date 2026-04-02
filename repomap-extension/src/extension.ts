import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";
import { EventWatcher } from "./EventWatcher";
import { LiveViewProvider } from "./LiveViewProvider";
import { RepomapEvent } from "./types";

let watcher: EventWatcher | undefined;
let statusItem: vscode.StatusBarItem | undefined;

export function activate(context: vscode.ExtensionContext): void {
  const log = vscode.window.createOutputChannel("RepoMap");
  log.appendLine("[repomap] activating extension");

  const proxyPath = path.join(context.extensionPath, "proxy.js");

  // --- Wrap the MCP config with our proxy ---
  wrapMcpConfig(proxyPath, log);

  // --- Sidebar webview ---
  const provider = new LiveViewProvider(context.extensionUri);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(LiveViewProvider.viewType, provider, {
      webviewOptions: { retainContextWhenHidden: true },
    })
  );

  // --- Event watcher ---
  watcher = new EventWatcher();
  watcher.clearLog();
  watcher.start();

  watcher.on("event", (ev: RepomapEvent) => {
    log.appendLine(`[repomap] ${ev.status}: ${ev.tool} (id=${ev.id})`);
    provider.pushEvent(ev);
    refreshStatusBar(ev);
  });

  context.subscriptions.push({ dispose: () => watcher?.stop() });

  // --- Status bar ---
  statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, -100);
  statusItem.command = "repomap.focusSidebar";
  statusItem.text = "$(symbol-structure) RepoMap";
  statusItem.tooltip = "RepoMap — waiting for MCP activity";
  statusItem.show();
  context.subscriptions.push(statusItem);

  // --- Commands ---
  context.subscriptions.push(
    vscode.commands.registerCommand("repomap.focusSidebar", () => {
      vscode.commands.executeCommand("repomap.liveView.focus");
    })
  );

  log.appendLine("[repomap] activated — proxy.js at " + proxyPath);
  log.appendLine("[repomap] watching ~/.repomap/events.jsonl");
}

export function deactivate(): void {
  watcher?.stop();
}

/**
 * Reads .cursor/mcp.json in every workspace folder (and global ~/.cursor/mcp.json).
 * If a "repomap" server entry exists, wraps its command with our proxy.js
 * so we can intercept all MCP traffic transparently.
 */
function wrapMcpConfig(proxyPath: string, log: vscode.OutputChannel): void {
  const candidates: string[] = [];

  for (const folder of vscode.workspace.workspaceFolders ?? []) {
    candidates.push(path.join(folder.uri.fsPath, ".cursor", "mcp.json"));
  }

  const home = process.env.HOME || process.env.USERPROFILE || "";
  if (home) {
    candidates.push(path.join(home, ".cursor", "mcp.json"));
  }

  for (const mcpPath of candidates) {
    try {
      if (!fs.existsSync(mcpPath)) continue;

      const raw = fs.readFileSync(mcpPath, "utf-8");
      const config = JSON.parse(raw);
      const servers: Record<string, McpServerEntry> = config.mcpServers ?? {};
      const entry = servers.repomap;
      if (!entry) continue;

      if (isAlreadyWrapped(entry, proxyPath)) {
        log.appendLine(`[repomap] ${mcpPath} already wrapped`);
        continue;
      }

      const origCommand = entry.command;
      const origArgs: string[] = entry.args ?? [];

      entry.command = "node";
      entry.args = [proxyPath, origCommand, ...origArgs];

      fs.writeFileSync(mcpPath, JSON.stringify(config, null, 2) + "\n");
      log.appendLine(`[repomap] wrapped ${mcpPath}: node proxy.js ${origCommand} ${origArgs.join(" ")}`);
    } catch (err) {
      log.appendLine(`[repomap] could not wrap ${mcpPath}: ${err}`);
    }
  }
}

function isAlreadyWrapped(entry: McpServerEntry, proxyPath: string): boolean {
  if (entry.command !== "node") return false;
  const args = entry.args ?? [];
  return args.length > 0 && args[0] === proxyPath;
}

function refreshStatusBar(ev: RepomapEvent): void {
  if (!statusItem) return;
  if (ev.status === "running") {
    statusItem.text = `$(sync~spin) RepoMap · ${ev.tool}`;
    statusItem.tooltip = `Running ${ev.tool}...`;
  } else if (ev.status === "error") {
    statusItem.text = `$(error) RepoMap · ${ev.tool} failed`;
    statusItem.tooltip = ev.error || "Tool call failed";
  } else {
    const label = ev.risk_level;
    statusItem.text = `$(symbol-structure) RepoMap · ${label}`;
    statusItem.tooltip = `${ev.tool}: ${ev.risk_score} risk (${label})`;
  }
}

interface McpServerEntry {
  command: string;
  args?: string[];
  cwd?: string;
}

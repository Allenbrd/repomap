import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import { execFile } from "child_process";
import { GraphData, RepomapEvent } from "./types";

export class GraphPanelProvider {
  private panel: vscode.WebviewPanel | undefined;
  private refreshTimer: ReturnType<typeof setInterval> | undefined;
  private ready = false;
  private pendingMessages: unknown[] = [];

  constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly log: vscode.OutputChannel
  ) {}

  openOrReveal(): void {
    if (this.panel) {
      this.panel.reveal(vscode.ViewColumn.Beside);
      return;
    }

    this.panel = vscode.window.createWebviewPanel(
      "repomap.graph",
      "⬡ RepoMap Graph",
      vscode.ViewColumn.Beside,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(this.extensionUri, "media")],
      }
    );

    this.panel.webview.html = this.getHtml();

    this.panel.webview.onDidReceiveMessage((msg) => {
      if (msg.type === "ready") {
        this.ready = true;
        this.loadGraph();
        for (const m of this.pendingMessages) this.post(m);
        this.pendingMessages = [];
      }
      if (msg.type === "nodeClick" && msg.path) {
        const ws = vscode.workspace.workspaceFolders?.[0];
        if (ws) {
          const uri = vscode.Uri.joinPath(ws.uri, msg.path);
          vscode.window.showTextDocument(uri, { preview: true });
        }
      }
    });

    this.panel.onDidDispose(() => {
      this.panel = undefined;
      this.ready = false;
      if (this.refreshTimer) clearInterval(this.refreshTimer);
    });

    this.refreshTimer = setInterval(() => this.refreshGraph(), 30_000);
  }

  sendEvent(ev: RepomapEvent): void {
    this.post({ type: "event", event: ev });
  }

  sendConnectionStatus(status: "connected" | "disconnected"): void {
    this.post({ type: "connection", status });
  }

  dispose(): void {
    if (this.refreshTimer) clearInterval(this.refreshTimer);
    this.panel?.dispose();
  }

  private post(msg: unknown): void {
    if (!this.ready) {
      this.pendingMessages.push(msg);
      return;
    }
    this.panel?.webview.postMessage(msg);
  }

  private async loadGraph(): Promise<void> {
    const data = await this.fetchGraphData();
    if (data) {
      this.post({ type: "init", graph: data });
    }
  }

  private async refreshGraph(): Promise<void> {
    const data = await this.fetchGraphData();
    if (data) {
      this.post({ type: "refresh", graph: data });
    }
  }

  private fetchGraphData(): Promise<GraphData | null> {
    return new Promise((resolve) => {
      const ws = vscode.workspace.workspaceFolders?.[0];
      if (!ws) { resolve(null); return; }

      const repoPath = ws.uri.fsPath;
      const scriptPath = path.join(this.extensionUri.fsPath, "graph_export.py");
      const pythonPath = this.findPython(repoPath);

      this.log.appendLine(`[graph] fetching graph: ${pythonPath} ${scriptPath} ${repoPath}`);

      const repomapRoot = this.findRepomapRoot();
      const env = { ...process.env };
      if (repomapRoot) {
        env.PYTHONPATH = path.join(repomapRoot, "src") + (env.PYTHONPATH ? ":" + env.PYTHONPATH : "");
      }

      execFile(pythonPath, [scriptPath, repoPath], {
        timeout: 30_000,
        maxBuffer: 10 * 1024 * 1024,
        env,
      }, (err, stdout, stderr) => {
        if (err) {
          this.log.appendLine(`[graph] export error: ${err.message}`);
          if (stderr) this.log.appendLine(`[graph] stderr: ${stderr}`);
          resolve(null);
          return;
        }
        try {
          const data = JSON.parse(stdout) as GraphData;
          this.log.appendLine(`[graph] loaded ${data.nodes.length} nodes, ${data.edges.length} edges`);
          resolve(data);
        } catch (e) {
          this.log.appendLine(`[graph] JSON parse error: ${e}`);
          resolve(null);
        }
      });
    });
  }

  private findPython(repoPath: string): string {
    const venvPy = path.join(repoPath, ".venv", "bin", "python");
    if (fs.existsSync(venvPy)) return venvPy;

    const repomapRoot = this.findRepomapRoot();
    if (repomapRoot) {
      const rmVenvPy = path.join(repomapRoot, ".venv", "bin", "python");
      if (fs.existsSync(rmVenvPy)) return rmVenvPy;
    }

    return process.platform === "win32" ? "python" : "python3";
  }

  private findRepomapRoot(): string | undefined {
    const extRoot = this.extensionUri.fsPath;
    const parent = path.dirname(extRoot);
    if (fs.existsSync(path.join(parent, "pyproject.toml"))) return parent;

    const home = process.env.HOME || "";
    const candidate = path.join(home, "dev", "repomap");
    if (fs.existsSync(path.join(candidate, "pyproject.toml"))) return candidate;

    return undefined;
  }

  private getHtml(): string {
    const htmlPath = path.join(this.extensionUri.fsPath, "media", "graph.html");
    return fs.readFileSync(htmlPath, "utf-8");
  }
}

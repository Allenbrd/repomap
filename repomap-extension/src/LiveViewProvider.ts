import * as vscode from "vscode";
import * as crypto from "crypto";
import { RepomapEvent } from "./types";

const MAX_RECENT = 10;

export class LiveViewProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "repomap.liveView";

  private view?: vscode.WebviewView;
  private current: RepomapEvent | null = null;
  private recent: RepomapEvent[] = [];

  constructor(private readonly extensionUri: vscode.Uri) {}

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    this.view = webviewView;
    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this.extensionUri, "media")],
    };
    this.render();
  }

  pushEvent(ev: RepomapEvent): void {
    if (ev.status === "running") {
      this.current = ev;
    } else {
      this.current = null;
      this.recent.unshift(ev);
      if (this.recent.length > MAX_RECENT) this.recent.pop();
    }
    this.render();
  }

  private render(): void {
    if (!this.view) return;
    const webview = this.view.webview;
    const nonce = crypto.randomBytes(16).toString("hex");
    const styleUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this.extensionUri, "media", "styles.css")
    );
    webview.html = this.buildHtml(nonce, styleUri.toString());
  }

  private buildHtml(nonce: string, styleHref: string): string {
    let body: string;

    if (this.current) {
      body = this.renderRunning(this.current);
    } else if (this.recent.length === 0) {
      body = this.renderIdle();
    } else {
      body = "";
    }

    if (this.recent.length > 0) {
      body += `<div class="rm-section-hdr"><span class="rm-blink">&#9632;</span> RECENT</div>`;
      for (const ev of this.recent) {
        body += this.renderCompleted(ev);
      }
    }

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta http-equiv="Content-Security-Policy"
    content="default-src 'none'; style-src ${this.view!.webview.cspSource} 'unsafe-inline'; img-src data:; script-src 'nonce-${nonce}';" />
  <link rel="stylesheet" href="${styleHref}" />
</head>
<body>
  <div class="rm-panel">${body}</div>
</body>
</html>`;
  }

  private renderIdle(): string {
    return `<div class="rm-idle">
  <div class="rm-idle-icon">&#x2B21;</div>
  <div class="rm-idle-title">REPOMAP IS WATCHING</div>
  <div class="rm-idle-sub">Waiting for agent activity&hellip;</div>
</div>`;
  }

  private renderRunning(ev: RepomapEvent): string {
    const args = this.fmtArgs(ev.args);
    return `<div class="rm-card">
  <div class="rm-label">${esc(ev.tool)}</div>
  <div class="rm-muted" style="margin-top:2px">${esc(args)}</div>
  <div class="rm-scan-track"><div class="rm-scan-fill"></div></div>
</div>`;
  }

  private renderCompleted(ev: RepomapEvent): string {
    if (ev.status === "error") {
      return `<div class="rm-card rm-card-error">
  <div style="display:flex;align-items:center;gap:6px">
    <span class="rm-label" style="color:var(--rm-critical)">${esc(ev.tool)}</span>
    <span class="rm-badge rm-badge-critical">ERROR</span>
    <span class="rm-faint" style="margin-left:auto">${this.fmtTime(ev.timestamp)}</span>
  </div>
  <div class="rm-error">${esc(ev.error || "Unknown error")}</div>
</div>`;
    }

    const lvl = ev.risk_level.toLowerCase();
    const pct = Math.round(ev.risk_score * 100);

    let violHtml = "";
    if (ev.violations.length > 0) {
      violHtml = ev.violations
        .map(
          (v) =>
            `<div class="rm-viol"><span class="rm-badge rm-badge-${v.severity === "critical" ? "critical" : "high"}" style="font-size:8px">${esc(v.zone.toUpperCase())}</span><span class="rm-muted">${esc(v.message)}</span></div>`
        )
        .join("");
    }

    let mermaidHtml = "";
    if (ev.mermaid_source) {
      mermaidHtml = `<div class="rm-mermaid">${esc(ev.mermaid_source)}</div>`;
    }

    return `<div class="rm-card">
  <div style="display:flex;align-items:center;gap:6px">
    <span class="rm-label">${esc(ev.tool)}</span>
    <span class="rm-badge rm-badge-${lvl}">${ev.risk_level}</span>
    <span class="rm-faint" style="margin-left:auto">${this.fmtTime(ev.timestamp)}</span>
  </div>
  <div class="rm-muted" style="margin-top:2px">${esc(this.fmtArgs(ev.args))}</div>
  <div class="rm-bar-track"><div class="rm-bar-fill rm-bar-fill-${lvl}" style="width:${pct}%"></div></div>
  <div style="font-size:10px;color:var(--rm-text)">${pct}% risk</div>
  ${ev.reasoning ? `<div class="rm-reasoning">${esc(ev.reasoning)}</div>` : ""}
  ${violHtml}
  ${mermaidHtml}
</div>`;
  }

  private fmtArgs(args: Record<string, string>): string {
    return Object.entries(args)
      .filter(([k]) => k !== "repo_path")
      .map(([k, v]) => `${k}: ${v}`)
      .join(" · ") || Object.entries(args).map(([k, v]) => `${k}: ${v}`).join(" · ");
  }

  private fmtTime(ts: string): string {
    try {
      return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch {
      return ts;
    }
  }
}

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

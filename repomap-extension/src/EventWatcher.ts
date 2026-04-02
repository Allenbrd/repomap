import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import { EventEmitter } from "events";
import {
  RepomapEvent,
  PolicyViolation,
  ProxyEvent,
  riskLevelFromScore,
} from "./types";

const LOG_FILE = path.join(os.homedir(), ".repomap", "events.jsonl");

/**
 * Tail-follows ~/.repomap/events.jsonl written by proxy.js.
 * Correlates "call" and "result"/"error" events by JSON-RPC id,
 * then emits full RepomapEvent objects.
 */
export class EventWatcher extends EventEmitter {
  private offset = 0;
  private watcher: fs.FSWatcher | null = null;
  private pending = new Map<number, { tool: string; args: Record<string, string>; ts: string }>();
  private debounce: ReturnType<typeof setTimeout> | null = null;

  start(): void {
    this.ensureLogFile();
    this.offset = this.fileSize();

    try {
      this.watcher = fs.watch(LOG_FILE, () => {
        if (this.debounce) clearTimeout(this.debounce);
        this.debounce = setTimeout(() => this.readNewLines(), 50);
      });
    } catch {
      /* file may not exist yet — retry on interval */
    }

    if (!this.watcher) {
      const interval = setInterval(() => {
        this.ensureLogFile();
        try {
          this.watcher = fs.watch(LOG_FILE, () => {
            if (this.debounce) clearTimeout(this.debounce);
            this.debounce = setTimeout(() => this.readNewLines(), 50);
          });
          clearInterval(interval);
        } catch {
          /* keep trying */
        }
      }, 2000);
    }
  }

  stop(): void {
    if (this.watcher) {
      this.watcher.close();
      this.watcher = null;
    }
    if (this.debounce) {
      clearTimeout(this.debounce);
      this.debounce = null;
    }
  }

  clearLog(): void {
    try {
      fs.writeFileSync(LOG_FILE, "");
      this.offset = 0;
      this.pending.clear();
    } catch {
      /* ignore */
    }
  }

  private ensureLogFile(): void {
    const dir = path.dirname(LOG_FILE);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    if (!fs.existsSync(LOG_FILE)) {
      fs.writeFileSync(LOG_FILE, "");
    }
  }

  private fileSize(): number {
    try {
      return fs.statSync(LOG_FILE).size;
    } catch {
      return 0;
    }
  }

  private readNewLines(): void {
    const size = this.fileSize();
    if (size <= this.offset) return;

    const buf = Buffer.alloc(size - this.offset);
    const fd = fs.openSync(LOG_FILE, "r");
    fs.readSync(fd, buf, 0, buf.length, this.offset);
    fs.closeSync(fd);
    this.offset = size;

    const text = buf.toString("utf-8");
    for (const line of text.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        this.handleLine(JSON.parse(trimmed) as ProxyEvent);
      } catch {
        /* skip malformed lines */
      }
    }
  }

  private handleLine(ev: ProxyEvent): void {
    if (ev.type === "call") {
      this.pending.set(ev.id, { tool: ev.tool, args: ev.args, ts: ev.ts });

      const running: RepomapEvent = {
        id: ev.id,
        tool: ev.tool,
        status: "running",
        timestamp: ev.ts,
        args: ev.args,
        risk_score: 0,
        risk_level: "LOW",
        reasoning: "",
        violations: [],
        mermaid_source: "",
      };
      this.emit("event", running);
      return;
    }

    if (ev.type === "result" && ev.id != null) {
      const call = this.pending.get(ev.id);
      this.pending.delete(ev.id);

      const parsed = parseMarkdownResult(ev.text);
      const completed: RepomapEvent = {
        id: ev.id,
        tool: call?.tool ?? ev.tool ?? "unknown",
        status: "completed",
        timestamp: ev.ts,
        args: call?.args ?? {},
        ...parsed,
      };
      this.emit("event", completed);
      return;
    }

    if (ev.type === "error") {
      const call = ev.id != null ? this.pending.get(ev.id) : undefined;
      if (ev.id != null) this.pending.delete(ev.id);

      const errEvent: RepomapEvent = {
        id: ev.id ?? 0,
        tool: call?.tool ?? ev.tool ?? "unknown",
        status: "error",
        timestamp: ev.ts,
        args: call?.args ?? {},
        risk_score: 0,
        risk_level: "LOW",
        reasoning: "",
        violations: [],
        mermaid_source: "",
        error: ev.error,
      };
      this.emit("event", errEvent);
    }
  }
}

/**
 * Extracts structured data from the MCP server's markdown response.
 * Patterns match format_blast_radius_text, format_execution_path_text, etc.
 */
function parseMarkdownResult(text: string): {
  risk_score: number;
  risk_level: RepomapEvent["risk_level"];
  reasoning: string;
  violations: PolicyViolation[];
  mermaid_source: string;
} {
  const scoreMatch = text.match(/\*\*Risk Score:\s*([\d.]+)\s*\((\w+)\)\*\*/);
  const riskScore = scoreMatch ? parseFloat(scoreMatch[1]) : 0;
  const riskLevel = riskLevelFromScore(riskScore);

  const violations: PolicyViolation[] = [];
  const violationRe = /(?:\u{1F534}|\u{1F7E1})\s*(CRITICAL|WARNING):\s*(.+)/gu;
  let vm: RegExpExecArray | null;
  while ((vm = violationRe.exec(text)) !== null) {
    const zoneMatch = vm[2].match(/reaches\s+(\w+)\s+zone/i);
    violations.push({
      zone: zoneMatch ? zoneMatch[1].toLowerCase() : "unknown",
      severity: vm[1].toLowerCase(),
      message: vm[2].trim(),
    });
  }

  const mermaidMatch = text.match(/```mermaid\n([\s\S]*?)```/);
  const mermaidSource = mermaidMatch ? mermaidMatch[1].trim() : "";

  let reasoning = "";
  const firstLine = text.split("\n")[0] || "";
  if (firstLine.startsWith("## ")) {
    reasoning = firstLine.replace(/^##\s*/, "");
  }

  const totalMatch = text.match(/\*\*Total affected files:\s*(\d+)\*\*/);
  if (totalMatch) {
    reasoning += ` — ${totalMatch[1]} affected files`;
  }

  const pathLenMatch = text.match(/\*\*Path length:\*\*\s*(\d+)/);
  const chainMatch = text.match(/\*\*Chain:\*\*\s*(.+)/);
  if (pathLenMatch) {
    reasoning += ` — ${pathLenMatch[1]} hops`;
  }
  if (chainMatch) {
    reasoning += `: ${chainMatch[1]}`;
  }

  if (text.includes("No dependency path exists")) {
    reasoning += " — no path found";
  }
  if (text.includes("No other files depend on this file")) {
    reasoning += " — safe to modify";
  }

  return { risk_score: riskScore, risk_level: riskLevel, reasoning: reasoning.trim(), violations, mermaid_source: mermaidSource };
}

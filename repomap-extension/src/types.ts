/**
 * Event types matching the MCP server's field names.
 *
 * risk_score  — from graph.py BlastRadiusResult
 * risk_level  — from formatter.py _risk_label (>=0.8 CRITICAL, >=0.6 HIGH, >=0.3 MEDIUM, else LOW)
 * policy zone fields — from policy.py PolicyViolation
 */

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface PolicyViolation {
  zone: string;
  severity: string;
  message: string;
}

export interface RepomapEvent {
  id: number | string;
  tool: string;
  status: "running" | "completed" | "error";
  timestamp: string;
  args: Record<string, string>;
  risk_score: number;
  risk_level: RiskLevel;
  reasoning: string;
  violations: PolicyViolation[];
  mermaid_source: string;
  error?: string;
}

export function riskLevelFromScore(score: number): RiskLevel {
  if (score >= 0.8) return "CRITICAL";
  if (score >= 0.6) return "HIGH";
  if (score >= 0.3) return "MEDIUM";
  return "LOW";
}

/**
 * Raw event line from the proxy JSONL log.
 */
export interface ProxyCallEvent {
  ts: string;
  type: "call";
  id: number;
  tool: string;
  args: Record<string, string>;
}

export interface ProxyResultEvent {
  ts: string;
  type: "result";
  id: number;
  tool: string;
  text: string;
}

export interface ProxyErrorEvent {
  ts: string;
  type: "error";
  id: number | null;
  tool: string | null;
  error: string;
}

export type ProxyEvent = ProxyCallEvent | ProxyResultEvent | ProxyErrorEvent;

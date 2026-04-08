import type {
  ActionResponse,
  AuditLogResponse,
  BacktestDetailResponse,
  BacktestRequestPayload,
  BacktestResponse,
  BacktestSummaryResponse,
  BotSettingsUpdatePayload,
  BotSettingsResponse,
  CommitteeDecision,
  ExecutionQualitySampleResponse,
  ExecutionQualitySummaryResponse,
  ExecutionIntentResponse,
  LiveEnablePrepareResponse,
  LoginResponse,
  OrderFillResponse,
  OrderResponse,
  OrderTransitionResponse,
  PositionResponse,
  ReconciliationMismatchResponse,
  RiskEventResponse,
  SessionResponse,
  OrderStatus,
  PerformanceSummaryResponse,
  TimeInForce,
  RunResponse
} from "@/lib/contracts";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type JsonBody = object | undefined;

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit & { json?: JsonBody }): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.json !== undefined) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
    body: init?.json !== undefined ? JSON.stringify(init.json) : init?.body
  });

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    const message =
      typeof payload === "string"
        ? payload
        : payload && typeof payload === "object" && "detail" in payload
          ? String(payload.detail)
          : `API request failed: ${response.status}`;
    throw new ApiError(message, response.status);
  }

  return payload as T;
}

export async function login(email: string, password: string) {
  return request<LoginResponse>("/auth/login", {
    method: "POST",
    json: { email, password }
  });
}

export async function getCurrentSession() {
  return request<LoginResponse>("/auth/me");
}

export async function logout() {
  return request<LoginResponse>("/auth/logout", { method: "POST" });
}

export async function listSessions(email?: string) {
  const params = new URLSearchParams();
  if (email) {
    params.set("email", email);
  }
  const query = params.toString();
  return request<SessionResponse[]>(`/auth/sessions${query ? `?${query}` : ""}`);
}

export async function revokeSession(sessionId: string) {
  return request<SessionResponse>(`/auth/sessions/${sessionId}/revoke`, { method: "POST" });
}

export async function getSettings() {
  return request<BotSettingsResponse>("/settings");
}

export async function updateSettings(payload: BotSettingsUpdatePayload) {
  return request<BotSettingsResponse>("/settings", {
    method: "PUT",
    json: payload
  });
}

export async function listRuns() {
  return request<RunResponse[]>("/runs?limit=8");
}

export async function listDecisions() {
  return request<CommitteeDecision[]>("/decisions?limit=12");
}

export async function listExecutionIntents(status?: string, limit = 20) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) {
    params.set("status", status);
  }
  return request<ExecutionIntentResponse[]>(`/execution-intents?${params.toString()}`);
}

export async function approveExecutionIntent(intentId: string) {
  return request<ExecutionIntentResponse>(`/execution-intents/${intentId}/approve`, { method: "POST" });
}

export async function rejectExecutionIntent(intentId: string, detail: string) {
  const params = new URLSearchParams({ detail });
  return request<ExecutionIntentResponse>(`/execution-intents/${intentId}/reject?${params.toString()}`, {
    method: "POST"
  });
}

export async function listOrders() {
  return request<OrderResponse[]>("/orders?limit=12");
}

export async function listOrderTransitions(orderId: number) {
  return request<OrderTransitionResponse[]>(`/orders/${orderId}/transitions`);
}

export async function listOrderFills(orderId: number) {
  return request<OrderFillResponse[]>(`/orders/${orderId}/fills`);
}

export async function replaceOrder(
  orderId: number,
  payload: {
    quantity?: number;
    limit_price?: number;
    stop_price?: number;
    take_profit?: number;
    time_in_force?: TimeInForce;
  }
) {
  return request<OrderResponse>(`/orders/${orderId}/replace`, { method: "POST", json: payload });
}

export async function cancelOrder(orderId: number) {
  return request<OrderResponse>(`/orders/${orderId}/cancel`, { method: "POST" });
}

export async function cancelAllOrders() {
  return request<{ canceled_orders: number; flatten_submitted: number }>("/orders/cancel-all", { method: "POST" });
}

export async function flattenAllPositions() {
  return request<{ canceled_orders: number; flatten_submitted: number }>("/bot/flatten-all", { method: "POST" });
}

export async function brokerKill() {
  return request<ActionResponse>("/bot/broker-kill", { method: "POST" });
}

export async function listPositions() {
  return request<PositionResponse[]>("/positions");
}

export async function listRiskEvents() {
  return request<RiskEventResponse[]>("/risk-events?limit=12");
}

export async function listAlerts(limit = 24) {
  return request<RiskEventResponse[]>(`/alerts?limit=${String(limit)}`);
}

export async function getPerformanceSummary(windowMinutes = 60) {
  return request<PerformanceSummaryResponse>(`/performance/summary?window_minutes=${String(windowMinutes)}`);
}

export async function listExecutionQualitySamples(
  symbol?: string,
  outcomeStatus?: OrderStatus,
  limit = 20
) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (symbol) {
    params.set("symbol", symbol.toUpperCase());
  }
  if (outcomeStatus) {
    params.set("outcome_status", outcomeStatus);
  }
  return request<ExecutionQualitySampleResponse[]>(`/execution-quality/samples?${params.toString()}`);
}

export async function listExecutionQualitySummary(
  dimension: "symbol" | "venue" | "broker" | "order_type" = "symbol",
  limit = 10
) {
  const params = new URLSearchParams({ dimension, limit: String(limit) });
  return request<ExecutionQualitySummaryResponse[]>(`/execution-quality/summary?${params.toString()}`);
}

export async function listAuditLogs(limit = 20) {
  return request<AuditLogResponse[]>(`/audit-logs?limit=${String(limit)}`);
}

export async function listReconciliationMismatches() {
  return request<ReconciliationMismatchResponse[]>("/reconciliation/mismatches?limit=50");
}

export async function runReconciliation() {
  return request<{
    transitions_applied: number;
    fills_ingested: number;
    mismatches_created: number;
    unresolved_mismatches: number;
    live_paused: number;
  }>("/reconciliation/run", { method: "POST" });
}

export async function launchBacktest(payload: BacktestRequestPayload) {
  return request<BacktestResponse>("/backtests", { method: "POST", json: payload });
}

export async function listBacktests(status?: string, limit = 20) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) {
    params.set("status", status);
  }
  return request<BacktestSummaryResponse[]>(`/backtests?${params.toString()}`);
}

export async function getBacktestReport(reportId: string) {
  return request<BacktestDetailResponse>(`/backtests/${reportId}`);
}

export async function startBot() {
  return request("/bot/start", { method: "POST" });
}

export async function stopBot() {
  return request("/bot/stop", { method: "POST" });
}

export async function switchMode(mode: "paper" | "live") {
  return request("/bot/mode", { method: "POST", json: { mode } });
}

export async function toggleKillSwitch(enabled: boolean) {
  return request(`/bot/kill-switch?enabled=${String(enabled)}`, { method: "POST" });
}

export async function prepareLiveEnablement() {
  return request<LiveEnablePrepareResponse>("/bot/live/prepare", { method: "POST" });
}

export async function enableLiveExecution(approvalCode: string) {
  return request<BotSettingsResponse>("/bot/live/enable", {
    method: "POST",
    json: { approval_code: approvalCode }
  });
}

export async function disableLiveExecution() {
  return request<BotSettingsResponse>("/bot/live/disable", { method: "POST" });
}

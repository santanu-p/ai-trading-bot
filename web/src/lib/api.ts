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
  MarketProfileSummaryResponse,
  OrderFillResponse,
  OrderResponse,
  OrderTransitionResponse,
  PositionResponse,
  ReconciliationMismatchResponse,
  RiskEventResponse,
  SessionResponse,
  TradeReviewResponse,
  TradeReviewSummaryResponse,
  OrderStatus,
  PerformanceSummaryResponse,
  TimeInForce,
  RunResponse
} from "@/lib/contracts";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
let csrfToken: string | null = null;

type JsonBody = object | undefined;
type ProfileScoped = { profileId?: number | null };

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
  if (init?.method && !["GET", "HEAD", "OPTIONS"].includes(init.method.toUpperCase()) && csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
    body: init?.json !== undefined ? JSON.stringify(init.json) : init?.body
  });
  const nextCsrfToken = response.headers.get("x-csrf-token");
  if (nextCsrfToken) {
    csrfToken = nextCsrfToken;
  }

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

function withProfile(path: string, profileId?: number | null) {
  if (!profileId) {
    return path;
  }
  const joiner = path.includes("?") ? "&" : "?";
  return `${path}${joiner}profile_id=${String(profileId)}`;
}

export async function login(email: string, password: string) {
  const response = await request<LoginResponse>("/auth/login", {
    method: "POST",
    json: { email, password }
  });
  csrfToken = response.csrf_token ?? csrfToken;
  return response;
}

export async function getCurrentSession() {
  const response = await request<LoginResponse>("/auth/me");
  csrfToken = response.csrf_token ?? csrfToken;
  return response;
}

export async function logout() {
  const response = await request<LoginResponse>("/auth/logout", { method: "POST" });
  csrfToken = response.csrf_token ?? null;
  return response;
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

export async function listProfiles() {
  return request<MarketProfileSummaryResponse[]>("/profiles");
}

export async function getSettings(profileId?: number | null) {
  if (profileId) {
    return request<BotSettingsResponse>(`/profiles/${profileId}/settings`);
  }
  return request<BotSettingsResponse>("/settings");
}

export async function updateSettings(profileId: number | null | undefined, payload: BotSettingsUpdatePayload) {
  const path = profileId ? `/profiles/${profileId}/settings` : "/settings";
  return request<BotSettingsResponse>(path, {
    method: "PUT",
    json: payload
  });
}

export async function listRuns({ profileId }: ProfileScoped = {}) {
  return request<RunResponse[]>(withProfile("/runs?limit=8", profileId));
}

export async function listDecisions({ profileId }: ProfileScoped = {}) {
  return request<CommitteeDecision[]>(withProfile("/decisions?limit=12", profileId));
}

export async function listExecutionIntents(status?: string, limit = 20, profileId?: number | null) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) {
    params.set("status", status);
  }
  if (profileId) {
    params.set("profile_id", String(profileId));
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

export async function listOrders({ profileId }: ProfileScoped = {}) {
  return request<OrderResponse[]>(withProfile("/orders?limit=12", profileId));
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

export async function cancelAllOrders(profileId?: number | null) {
  return request<{ canceled_orders: number; flatten_submitted: number }>(withProfile("/orders/cancel-all", profileId), {
    method: "POST"
  });
}

export async function flattenAllPositions(profileId?: number | null) {
  return request<{ canceled_orders: number; flatten_submitted: number }>(withProfile("/bot/flatten-all", profileId), {
    method: "POST"
  });
}

export async function brokerKill(profileId?: number | null) {
  return request<ActionResponse>(withProfile("/bot/broker-kill", profileId), { method: "POST" });
}

export async function listPositions({ profileId }: ProfileScoped = {}) {
  return request<PositionResponse[]>(withProfile("/positions", profileId));
}

export async function listRiskEvents({ profileId }: ProfileScoped = {}) {
  return request<RiskEventResponse[]>(withProfile("/risk-events?limit=12", profileId));
}

export async function listAlerts(limit = 24, profileId?: number | null) {
  return request<RiskEventResponse[]>(withProfile(`/alerts?limit=${String(limit)}`, profileId));
}

export async function getPerformanceSummary(windowMinutes = 60, profileId?: number | null) {
  return request<PerformanceSummaryResponse>(
    withProfile(`/performance/summary?window_minutes=${String(windowMinutes)}`, profileId)
  );
}

export async function listExecutionQualitySamples(
  symbol?: string,
  outcomeStatus?: OrderStatus,
  limit = 20,
  profileId?: number | null
) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (symbol) {
    params.set("symbol", symbol.toUpperCase());
  }
  if (outcomeStatus) {
    params.set("outcome_status", outcomeStatus);
  }
  if (profileId) {
    params.set("profile_id", String(profileId));
  }
  return request<ExecutionQualitySampleResponse[]>(`/execution-quality/samples?${params.toString()}`);
}

export async function listExecutionQualitySummary(
  dimension: "symbol" | "venue" | "broker" | "order_type" = "symbol",
  limit = 10,
  profileId?: number | null
) {
  const params = new URLSearchParams({ dimension, limit: String(limit) });
  if (profileId) {
    params.set("profile_id", String(profileId));
  }
  return request<ExecutionQualitySummaryResponse[]>(`/execution-quality/summary?${params.toString()}`);
}

export async function listAuditLogs(limit = 20, profileId?: number | null) {
  return request<AuditLogResponse[]>(withProfile(`/audit-logs?limit=${String(limit)}`, profileId));
}

export async function listTradeReviews(status?: string, limit = 20, profileId?: number | null) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) {
    params.set("status", status);
  }
  if (profileId) {
    params.set("profile_id", String(profileId));
  }
  return request<TradeReviewResponse[]>(`/trade-reviews?${params.toString()}`);
}

export async function summarizeTradeReviews(limit = 50, profileId?: number | null) {
  return request<TradeReviewSummaryResponse[]>(
    withProfile(`/trade-reviews/summary?limit=${String(limit)}`, profileId)
  );
}

export async function listReconciliationMismatches(profileId?: number | null) {
  return request<ReconciliationMismatchResponse[]>(
    withProfile("/reconciliation/mismatches?limit=50", profileId)
  );
}

export async function runReconciliation(profileId?: number | null) {
  return request<{
    transitions_applied: number;
    fills_ingested: number;
    mismatches_created: number;
    unresolved_mismatches: number;
    live_paused: number;
  }>(withProfile("/reconciliation/run", profileId), { method: "POST" });
}

export async function launchBacktest(payload: BacktestRequestPayload) {
  return request<BacktestResponse>("/backtests", { method: "POST", json: payload });
}

export async function listBacktests(status?: string, limit = 20, profileId?: number | null) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) {
    params.set("status", status);
  }
  if (profileId) {
    params.set("profile_id", String(profileId));
  }
  return request<BacktestSummaryResponse[]>(`/backtests?${params.toString()}`);
}

export async function getBacktestReport(reportId: string) {
  return request<BacktestDetailResponse>(`/backtests/${reportId}`);
}

export async function startBot(profileId?: number | null) {
  return request(withProfile("/bot/start", profileId), { method: "POST" });
}

export async function stopBot(profileId?: number | null) {
  return request(withProfile("/bot/stop", profileId), { method: "POST" });
}

export async function switchMode(mode: "paper" | "live", profileId?: number | null) {
  return request(withProfile("/bot/mode", profileId), { method: "POST", json: { mode } });
}

export async function toggleKillSwitch(enabled: boolean, profileId?: number | null) {
  return request(withProfile(`/bot/kill-switch?enabled=${String(enabled)}`, profileId), { method: "POST" });
}

export async function prepareLiveEnablement(profileId?: number | null) {
  return request<LiveEnablePrepareResponse>(withProfile("/bot/live/prepare", profileId), { method: "POST" });
}

export async function enableLiveExecution(approvalCode: string, profileId?: number | null) {
  return request<BotSettingsResponse>(withProfile("/bot/live/enable", profileId), {
    method: "POST",
    json: { approval_code: approvalCode }
  });
}

export async function disableLiveExecution(profileId?: number | null) {
  return request<BotSettingsResponse>(withProfile("/bot/live/disable", profileId), { method: "POST" });
}

export function openOperationsStream(
  onSnapshot: (payload: Record<string, unknown>) => void,
  onStatus?: (status: "open" | "error" | "closed") => void,
  profileId?: number | null
) {
  const stream = new EventSource(`${API_BASE_URL}${withProfile("/stream/operations", profileId)}`, { withCredentials: true });
  stream.addEventListener("operations.snapshot", (event) => {
    const message = event as MessageEvent<string>;
    onSnapshot(JSON.parse(message.data) as Record<string, unknown>);
  });
  stream.onopen = () => onStatus?.("open");
  stream.onerror = () => onStatus?.("error");
  return () => {
    onStatus?.("closed");
    stream.close();
  };
}

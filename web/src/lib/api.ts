import type {
  BotSettingsUpdatePayload,
  BotSettingsResponse,
  CommitteeDecision,
  OrderResponse,
  PositionResponse,
  RiskEventResponse,
  RunResponse
} from "@/lib/contracts";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type JsonBody = Record<string, unknown> | undefined;

async function request<T>(path: string, token: string, init?: RequestInit & { json?: JsonBody }): Promise<T> {
  const headers = new Headers(init?.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  headers.set("Accept", "application/json");
  if (init?.json) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    body: init?.json ? JSON.stringify(init.json) : init?.body
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `API request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function login(email: string, password: string) {
  return request<{ access_token: string; expires_in_minutes: number }>("/auth/login", "", {
    method: "POST",
    json: { email, password }
  });
}

export async function getSettings(token: string) {
  return request<BotSettingsResponse>("/settings", token);
}

export async function updateSettings(token: string, payload: BotSettingsUpdatePayload) {
  return request<BotSettingsResponse>("/settings", token, {
    method: "PUT",
    json: payload
  });
}

export async function listRuns(token: string) {
  return request<RunResponse[]>("/runs?limit=8", token);
}

export async function listDecisions(token: string) {
  return request<CommitteeDecision[]>("/decisions?limit=12", token);
}

export async function listOrders(token: string) {
  return request<OrderResponse[]>("/orders?limit=12", token);
}

export async function listPositions(token: string) {
  return request<PositionResponse[]>("/positions", token);
}

export async function listRiskEvents(token: string) {
  return request<RiskEventResponse[]>("/risk-events?limit=12", token);
}

export async function startBot(token: string) {
  return request("/bot/start", token, { method: "POST" });
}

export async function stopBot(token: string) {
  return request("/bot/stop", token, { method: "POST" });
}

export async function switchMode(token: string, mode: "paper" | "live") {
  return request("/bot/mode", token, { method: "POST", json: { mode } });
}

export async function toggleKillSwitch(token: string, enabled: boolean) {
  return request(`/bot/kill-switch?enabled=${String(enabled)}`, token, { method: "POST" });
}

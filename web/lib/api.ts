import type {
  ExampleSession,
  ReadyResponse,
  SessionResponse,
  TurnResponse,
} from "./contracts";

const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"
).replace(/\/$/, "");

export class ApiError extends Error {
  code: string;
  retryable: boolean;

  constructor(message: string, code = "request_error", retryable = false) {
    super(message);
    this.code = code;
    this.retryable = retryable;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = payload?.error || payload?.detail || {};
    throw new ApiError(
      error.message || "The shopping service is unavailable.",
      error.code || "request_error",
      Boolean(error.retryable),
    );
  }
  return payload as T;
}

export function getReady(): Promise<ReadyResponse> {
  return fetch(`${API_BASE}/readyz`)
    .then((response) => response.json())
    .catch(() => ({
      status: "initializing" as const,
      catalog_size: null,
      startup_seconds: null,
      message: null,
    }));
}

export function getExamples(): Promise<{ examples: ExampleSession[] }> {
  return request("/v1/examples");
}

export function createSession(options: {
  semantic: boolean;
}): Promise<SessionResponse> {
  return request("/v1/sessions", {
    method: "POST",
    body: JSON.stringify({
      mode: "demo",
      user_profile: {},
      include_trace: true,
      semantic: options.semantic,
    }),
  });
}

export function sendTurn(
  sessionId: string,
  body: { message: string },
): Promise<TurnResponse> {
  return request(`/v1/sessions/${sessionId}/turns`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function resetSession(sessionId: string): Promise<SessionResponse> {
  return request(`/v1/sessions/${sessionId}/reset`, { method: "POST" });
}

import type { DemoMode, SessionResponse, TurnResponse } from "./contracts";

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

export function createSession(mode: DemoMode): Promise<SessionResponse> {
  return request("/v1/sessions", {
    method: "POST",
    body: JSON.stringify({ mode, user_profile: {} }),
  });
}

export function sendTurn(
  sessionId: string,
  body: { message?: string; option_id?: string },
): Promise<TurnResponse> {
  return request(`/v1/sessions/${sessionId}/turns`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function resetSession(sessionId: string): Promise<SessionResponse> {
  return request(`/v1/sessions/${sessionId}/reset`, { method: "POST" });
}


import type { RecommendationRequest, RecommendationResponse, HealthResponse, MetricsResponse, ExperimentInfo } from '../types'

const API_BASE = '/api/v1'

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

async function getHealth(): Promise<HealthResponse> {
  const res = await fetch('/health', { cache: 'no-store' })
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`)
  return res.json()
}

export const api = {
  health: getHealth,

  recommend: (body: RecommendationRequest) =>
    request<RecommendationResponse>('/recommend', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  recommendGraph: (body: RecommendationRequest) =>
    request<RecommendationResponse>('/recommend/graph', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  getExperiments: () =>
    request<Record<string, ExperimentInfo>>('/experiments'),

  getMetrics: () =>
    request<MetricsResponse>('/metrics'),

  recordOutcome: (experimentId: string, group: string, success: boolean) =>
    request<{ status: string }>(`/experiments/${experimentId}/outcome?group=${group}&success=${success}`, {
      method: 'POST',
    }),
}

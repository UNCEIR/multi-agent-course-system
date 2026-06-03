import type { RecommendationRequest, RecommendationResponse, HealthResponse, MetricsResponse, ExperimentInfo, SSEEvent } from '../types'

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

  recommendReact: (body: RecommendationRequest) =>
    request<RecommendationResponse>('/recommend/react', {
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

  async *recommendStream(body: RecommendationRequest): AsyncGenerator<SSEEvent> {
    const res = await fetch(`${API_BASE}/recommend/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      let eventType = ''
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          const raw = line.slice(6)
          try {
            const data = JSON.parse(raw)
            yield { event: eventType, data } as SSEEvent
          } catch {
            // skip unparseable lines
          }
          eventType = ''
        }
      }
    }
  },

  async *recommendReactStream(body: RecommendationRequest): AsyncGenerator<SSEEvent> {
    const res = await fetch(`${API_BASE}/recommend/react/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      let eventType = ''
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          const raw = line.slice(6)
          try {
            const data = JSON.parse(raw)
            yield { event: eventType, data } as SSEEvent
          } catch {
            // skip unparseable lines
          }
          eventType = ''
        }
      }
    }
  },
}

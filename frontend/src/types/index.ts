export interface Course {
  course_id: string
  course_name: string
  teacher: string
  credits: number
  course_type: string
  course_category: string
  domain: string
  campus: string
  time_slot: string
  location: string
  capacity: number
  current_enrolled: number
  current_enrollment_ratio: number
  popularity_level: number
  rush_advice: string
  description: string
  assessment: string
  difficulty: string
  workload: string
  grade_friendly: string
  has_exam: number
  group_work_required: number
  suitable_for: string
  tags: string[]
  score: number
  match_reasons: string[]
}

export interface AgentResult {
  agent_name: string
  success: boolean
  latency_ms: number
  error: string | null
  data: Record<string, unknown>
  confidence: number
}

export interface RecommendationRequest {
  user_id: string
  scene?: string
  num_items?: number
  context?: Record<string, unknown>
  query?: string
  prompt?: string
  device_type?: string
}

export interface RecommendationResponse {
  request_id: string
  user_id: string
  courses: Course[]
  recommendation_reasons: Array<Record<string, string>>
  selection_warnings: Array<Record<string, unknown>>
  experiment_group: string
  agent_results: Record<string, AgentResult>
  agent_latencies: Record<string, number>
  total_latency_ms: number
  timestamp: string
}

export interface HealthResponse {
  status: string
  model: string
  llm: {
    model: string
    base_url_host: string
    looks_like_dashscope: boolean
  }
  embedding_provider: string
  deps: {
    mysql: boolean
    redis: boolean
    milvus: boolean
  }
}

export interface ExperimentGroup {
  name: string
  weight: number
  config: Record<string, unknown>
  successes: number
  failures: number
}

export interface ExperimentInfo {
  name: string
  enabled: boolean
  groups: ExperimentGroup[]
  stats: Record<string, unknown>
}

export interface MetricsResponse {
  agents: Record<string, { total_calls: number; success_rate: number; avg_latency_ms: number }>
  business: Record<string, unknown>
}

export interface PresetQuery {
  id: string
  label: string
  icon: string
  prompt: string
}

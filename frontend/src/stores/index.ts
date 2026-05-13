import { create } from 'zustand'
import type { RecommendationResponse, AgentResult } from '../types'

interface RecommendJob {
  id: string
  label: string
  prompt: string
  loading: boolean
  response: RecommendationResponse | null
  error: string | null
  startTime: number
}

interface RecommendStore {
  jobs: RecommendJob[]
  addJob: (id: string, label: string, prompt: string) => void
  setLoading: (id: string, loading: boolean) => void
  setResponse: (id: string, response: RecommendationResponse) => void
  setError: (id: string, error: string) => void
  removeJob: (id: string) => void
  clearJobs: () => void
}

export const useRecommendStore = create<RecommendStore>((set) => ({
  jobs: [],
  addJob: (id, label, prompt) =>
    set((s) => {
      const existing = s.jobs.find((j) => j.id === id)
      if (existing) {
        return {
          jobs: s.jobs.map((j) =>
            j.id === id
              ? { ...j, label, prompt, loading: true, response: null, error: null, startTime: Date.now() }
              : j
          ),
        }
      }
      return {
        jobs: [...s.jobs, { id, label, prompt, loading: true, response: null, error: null, startTime: Date.now() }],
      }
    }),
  setLoading: (id, loading) =>
    set((s) => ({
      jobs: s.jobs.map((j) => (j.id === id ? { ...j, loading } : j)),
    })),
  setResponse: (id, response) =>
    set((s) => ({
      jobs: s.jobs.map((j) => (j.id === id ? { ...j, loading: false, response, error: null } : j)),
    })),
  setError: (id, error) =>
    set((s) => ({
      jobs: s.jobs.map((j) => (j.id === id ? { ...j, loading: false, error } : j)),
    })),
  removeJob: (id) =>
    set((s) => ({ jobs: s.jobs.filter((j) => j.id !== id) })),
  clearJobs: () => set({ jobs: [] }),
}))

interface ActiveJobStore {
  activeId: string | null
  setActive: (id: string | null) => void
}

export const useActiveJobStore = create<ActiveJobStore>((set) => ({
  activeId: null,
  setActive: (id) => set({ activeId: id }),
}))

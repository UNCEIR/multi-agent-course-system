'use client'

import { create } from 'zustand'
import type { SessionInfo } from '../types'

const STORAGE_KEY = (userId: string) => `campus_sessions_${userId}`

interface SessionState {
  userId: string
  sessions: SessionInfo[]
  activeSessionId: string | null
  loading: boolean
  setUser: (userId: string) => void
  setSessions: (sessions: SessionInfo[]) => void
  setActive: (sessionId: string | null) => void
  newSession: () => string
  removeSession: (sessionId: string) => void
  persist: () => void
}

export const useSessionStore = create<SessionState>((set, get) => ({
  userId: '',
  sessions: [],
  activeSessionId: null,
  loading: false,
  setUser: (userId) => {
    let sessions: SessionInfo[] = []
    let active: string | null = null
    if (typeof window !== 'undefined' && userId) {
      try {
        const raw = window.localStorage.getItem(STORAGE_KEY(userId))
        if (raw) {
          const data = JSON.parse(raw)
          sessions = data.sessions ?? []
          active = data.activeSessionId ?? null
        }
      } catch {
        sessions = []
      }
    }
    set({ userId, sessions, activeSessionId: active })
  },
  setSessions: (sessions) => {
    set({ sessions })
    get().persist()
  },
  setActive: (sessionId) => {
    set({ activeSessionId: sessionId })
    get().persist()
  },
  newSession: () => {
    const id = `session_${Date.now()}`
    set({ activeSessionId: id })
    get().persist()
    return id
  },
  removeSession: (sessionId) => {
    set((s) => ({
      sessions: s.sessions.filter((x) => x.session_id !== sessionId),
      activeSessionId: s.activeSessionId === sessionId ? null : s.activeSessionId,
    }))
    get().persist()
  },
  persist: () => {
    const { userId, sessions, activeSessionId } = get()
    if (typeof window === 'undefined' || !userId) return
    try {
      window.localStorage.setItem(
        STORAGE_KEY(userId),
        JSON.stringify({ sessions, activeSessionId })
      )
    } catch {
      // 存储满/禁用时静默失败（会话仍由后端持久）
    }
  },
}))

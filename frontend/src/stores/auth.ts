'use client'

import { create } from 'zustand'
import type { AuthUser } from '../types'

const STORAGE_KEY = 'campus_auth_v1'

interface AuthState {
  user: AuthUser | null
  token: string
  hydrated: boolean
  login: (user: AuthUser, token: string) => void
  logout: () => void
  hydrate: () => void
}

function readStored(): { user: AuthUser | null; token: string } {
  if (typeof window === 'undefined') return { user: null, token: '' }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return { user: null, token: '' }
    const data = JSON.parse(raw)
    return { user: data.user ?? null, token: data.token ?? '' }
  } catch {
    return { user: null, token: '' }
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: '',
  hydrated: false,
  login: (user, token) => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ user, token }))
    }
    set({ user, token, hydrated: true })
  },
  logout: () => {
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(STORAGE_KEY)
    }
    set({ user: null, token: '', hydrated: true })
  },
  hydrate: () => {
    const { user, token } = readStored()
    set({ user, token, hydrated: true })
  },
}))

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { UserSummary } from '@/api/types'

interface AuthState {
  token: string | null
  user: UserSummary | null
  setAuth: (token: string, user: UserSummary) => void
  clearAuth: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setAuth: (token, user) => set({ token, user }),
      clearAuth: () => set({ token: null, user: null }),
    }),
    { name: 'ddm-auth' },
  ),
)

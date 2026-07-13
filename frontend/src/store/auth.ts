import { create } from 'zustand'
import { authApi, type UserInfo } from '@/api/auth'

interface AuthState {
  token: string | null
  user: UserInfo | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  fetchMe: () => Promise<void>
  logout: () => Promise<void>
  isAdmin: () => boolean
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: localStorage.getItem('token'),
  user: null,
  loading: false,

  login: async (username, password) => {
    const { data } = await authApi.login(username, password)
    localStorage.setItem('token', data.access_token)
    set({ token: data.access_token })
    await get().fetchMe()
  },

  fetchMe: async () => {
    set({ loading: true })
    try {
      const { data } = await authApi.me()
      set({ user: data })
    } finally {
      set({ loading: false })
    }
  },

  logout: async () => {
    try {
      await authApi.logout()
    } finally {
      localStorage.removeItem('token')
      set({ token: null, user: null })
    }
  },

  isAdmin: () => get().user?.role === 'admin',
}))

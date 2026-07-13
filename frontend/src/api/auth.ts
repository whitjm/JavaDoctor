import client from './client'

export interface UserInfo {
  id: number
  username: string
  role: 'admin' | 'user'
  is_active: boolean
  created_at: string
}

export const authApi = {
  register: (username: string, password: string) =>
    client.post('/auth/register', { username, password }),

  login: (username: string, password: string) =>
    client.post<{ access_token: string; token_type: string }>('/auth/login', {
      username,
      password,
    }),

  logout: () => client.post('/auth/logout'),

  me: () => client.get<UserInfo>('/auth/me'),

  changePassword: (old_password: string, new_password: string) =>
    client.put('/auth/password', { old_password, new_password }),
}

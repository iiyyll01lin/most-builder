import { apiClient } from './client'
import type { LoginRequest, TokenResponse, UserSummary } from './types'

export async function login(payload: LoginRequest): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>('/auth/login', payload)
  return data
}

export async function getMe(): Promise<UserSummary> {
  const { data } = await apiClient.get<UserSummary>('/auth/me')
  return data
}

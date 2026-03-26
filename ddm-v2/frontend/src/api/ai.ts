import { apiClient } from './client'
import type { SOPAction } from './types'

export interface GenerateSopRequest {
  instruction: string
  project_id?: string
}

export interface GenerateSopResponse {
  actions: SOPAction[]
  message: string
}

export async function generateSopActions(body: GenerateSopRequest): Promise<GenerateSopResponse> {
  const { data } = await apiClient.post<GenerateSopResponse>('/ai/generate-sop', body)
  return data
}

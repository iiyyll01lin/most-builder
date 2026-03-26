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

// ─── SOP Conflict Review ───────────────────────────────────────────────────────

export type ConflictSeverity = 'High' | 'Medium' | 'Low'

export interface SopConflict {
  severity: ConflictSeverity
  description: string
  related_action_ids: string[]
  suggestion: string
}

export interface SopReviewResponse {
  conflicts: SopConflict[]
  reviewed_action_count: number
  summary: string
}

export async function reviewSopActions(sopVersionId: string): Promise<SopReviewResponse> {
  const { data } = await apiClient.post<SopReviewResponse>('/ai/review-sop', {
    sop_version_id: sopVersionId,
  })
  return data
}


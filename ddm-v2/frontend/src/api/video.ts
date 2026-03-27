import { apiClient } from './client'
import type { VideoUpload, VisionAnalysisResponse } from './types'

// ─── Video upload ─────────────────────────────────────────────────────────────

export async function fetchUploads(sopVersionId: string): Promise<VideoUpload[]> {
  const res = await apiClient.get<VideoUpload[]>(`/video/uploads/${sopVersionId}`)
  return res.data
}

export async function fetchUpload(uploadId: string): Promise<VideoUpload> {
  const res = await apiClient.get<VideoUpload>(`/video/${uploadId}`)
  return res.data
}

export async function uploadVideo(sopVersionId: string, file: File): Promise<VideoUpload> {
  const form = new FormData()
  form.append('file', file)
  const res = await apiClient.post<VideoUpload>(`/video/upload/${sopVersionId}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

export async function deleteUpload(uploadId: string): Promise<void> {
  await apiClient.delete(`/video/${uploadId}`)
}

/**
 * Returns a URL string that the browser fetches directly with HTTP Range
 * support.  No async needed — the value is derived purely from the upload ID.
 */
export function getStreamUrl(uploadId: string): string {
  return `/api/v1/video/stream/${uploadId}`
}

// ─── Vision analysis ──────────────────────────────────────────────────────────

export async function triggerAnalysis(uploadId: string): Promise<VisionAnalysisResponse> {
  const res = await apiClient.post<VisionAnalysisResponse>(`/video/analyze/${uploadId}`)
  return res.data
}

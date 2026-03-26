import { apiClient } from './client'
import type { SOPVersion, SOPAction } from './types'

export async function getSopVersion(sopId: string): Promise<SOPVersion> {
  const { data } = await apiClient.get<SOPVersion>(`/sop/versions/${sopId}`)
  return data
}

export async function updateSopActions(
  sopId: string,
  actions: SOPAction[],
): Promise<SOPVersion> {
  const { data } = await apiClient.put<SOPVersion>(
    `/sop/versions/${sopId}/actions`,
    actions,
  )
  return data
}

export async function updateSopStatus(
  sopId: string,
  status: string,
): Promise<SOPVersion> {
  const { data } = await apiClient.put<SOPVersion>(
    `/sop/versions/${sopId}/status`,
    { status },
  )
  return data
}

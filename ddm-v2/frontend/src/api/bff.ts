import { apiClient } from './client'
import type { DashboardResponse } from './types'

export async function fetchDashboard(
  projectId: string,
  sopVersionId?: string,
): Promise<DashboardResponse> {
  const params = sopVersionId ? { sop_version_id: sopVersionId } : {}
  const { data } = await apiClient.get<DashboardResponse>(
    `/bff/dashboard/${projectId}`,
    { params },
  )
  return data
}

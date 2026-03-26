import { apiClient } from './client'
import type { MINamingValidateRequest, MINamingValidateResponse } from './types'

export async function validateMiNaming(
  payload: MINamingValidateRequest,
): Promise<MINamingValidateResponse> {
  const { data } = await apiClient.post<MINamingValidateResponse>(
    '/mi-naming/validate',
    payload,
  )
  return data
}

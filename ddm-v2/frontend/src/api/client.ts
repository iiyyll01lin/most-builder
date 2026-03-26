import axios, { AxiosError } from 'axios'
import toast from 'react-hot-toast'
import type { ApiErrorBody, ErrorCode } from './types'
import { useAuthStore } from '@/store/authStore'

// ─── Error code → human-readable label ───────────────────────────────────────

const ERROR_LABELS: Record<ErrorCode, string> = {
  NOT_FOUND: 'Resource Not Found',
  FORBIDDEN: 'Access Denied',
  UNAUTHORIZED: 'Session Expired',
  VALIDATION_ERROR: 'Validation Error',
  INVALID_STATUS_TRANSITION: 'Invalid Status Transition',
  CONFLICT: 'Conflict',
  BAD_REQUEST: 'Bad Request',
  INTERNAL_ERROR: 'Server Error',
}

// ─── Typed API error ──────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public readonly errorCode: ErrorCode,
    message: string,
    public readonly detail: ApiErrorBody['detail'],
    public readonly httpStatus: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

// ─── Axios instance ───────────────────────────────────────────────────────────

export const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// Inject bearer token from Zustand store on every request.
apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Map backend error responses to typed ApiError + toast notifications.
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorBody>) => {
    const status = error.response?.status ?? 0
    const data = error.response?.data

    // Handle structured backend error
    if (data && typeof data === 'object' && 'error_code' in data) {
      const errorCode = data.error_code as ErrorCode
      const label = ERROR_LABELS[errorCode] ?? 'Error'
      const detail = data.detail

      // Build detail string for validation errors
      let body = data.message
      if (detail && Array.isArray(detail) && detail.length > 0) {
        const fields = detail
          .map((d) => `• ${d.field}: ${d.message}`)
          .join('\n')
        body = `${data.message}\n${fields}`
      }

      // Auto-logout on 401
      if (errorCode === 'UNAUTHORIZED') {
        useAuthStore.getState().clearAuth()
        toast.error('Session expired. Please log in again.', { id: 'auth-expired' })
      } else {
        toast.error(`[${label}] ${body}`, { duration: 5000 })
      }

      throw new ApiError(errorCode, data.message, data.detail, status)
    }

    // Fallback for non-structured errors (network errors, etc.)
    const message = error.message || 'Network error'
    toast.error(message)
    throw new ApiError('INTERNAL_ERROR', message, null, status)
  },
)

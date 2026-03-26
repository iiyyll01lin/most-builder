import { apiClient } from './client'
import type { EmployeeEntry, ObjectEntry, StationEntry } from './types'

export async function fetchEmployees(): Promise<EmployeeEntry[]> {
  const { data } = await apiClient.get<EmployeeEntry[]>('/master/employees')
  return Array.isArray(data) ? data : (data as { items?: EmployeeEntry[] }).items ?? []
}

export async function fetchObjects(): Promise<ObjectEntry[]> {
  const { data } = await apiClient.get<ObjectEntry[]>('/master/objects')
  return Array.isArray(data) ? data : (data as { items?: ObjectEntry[] }).items ?? []
}

export async function fetchStations(): Promise<StationEntry[]> {
  const { data } = await apiClient.get<StationEntry[]>('/master/stations')
  return Array.isArray(data) ? data : (data as { items?: StationEntry[] }).items ?? []
}

import { apiClient } from './client'
import type { SaveRecord, SaveResponse, TaskAccepted } from './types'

// Updated 2026-01-16: Use microservices API v1 endpoints instead of monolith

export async function getSaves(params?: {
  limit?: number
  offset?: number
}): Promise<SaveRecord[]> {
  const response = await apiClient.get<SaveRecord[]>('/v1/admin/saves', {
    params: {
      limit: params?.limit ?? 200,
      offset: params?.offset ?? 0,
    },
  })
  return response.data
}

export async function getArchivers(): Promise<string[]> {
  const response = await apiClient.get<string[]>('/v1/admin/archivers')
  return response.data
}

export type CreateSavePayload = {
  url: string
  id: string
  archiver: string
}

export async function runArchiver({
  url,
  id,
  archiver,
}: CreateSavePayload): Promise<SaveResponse | TaskAccepted> {
  const trimmedArchiver = archiver.trim() || 'all'
  if (trimmedArchiver === 'all') {
    const response = await apiClient.post<TaskAccepted>('/v1/save', { url, id })
    return response.data
  }
  const response = await apiClient.post<SaveResponse>(`/v1/archive/${encodeURIComponent(trimmedArchiver)}`, {
    url,
    id,
  })
  return response.data
}

import { apiClient } from './client'
import type { SaveRecord, SaveResponse, TaskAccepted } from './types'

// Updated 2026-01-16: Use consolidated API endpoints

export async function getSaves(params?: {
  limit?: number
  offset?: number
}): Promise<SaveRecord[]> {
  const response = await apiClient.get<SaveRecord[]>('/v1/archives', {
    params: {
      limit: params?.limit ?? 200,
      offset: params?.offset ?? 0,
    },
  })
  return response.data
}

export async function getArchivers(): Promise<string[]> {
  const response = await apiClient.get<string[]>('/v1/system/archivers')
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
  const archivers = trimmedArchiver === 'all' ? ['all'] : [trimmedArchiver]

  const response = await apiClient.post<TaskAccepted>('/v1/archives', {
    items: [{ id, url }],
    archivers,
  })
  return response.data
}

import { apiClient } from './client'
import type { HtSendResponse } from './types'

// Updated 2026-01-16: Use microservices API v1 endpoint instead of monolith

export async function sendHtCommand({
  payload,
  waitMarker,
  timeout,
}: {
  payload: string
  waitMarker?: string
  timeout?: number
}): Promise<HtSendResponse> {
  const params = new URLSearchParams({ payload })
  const response = await apiClient.post<HtSendResponse>('/v1/ht/send', params, {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    params: {
      wait_marker: waitMarker,
      timeout,
    },
  })
  return response.data
}

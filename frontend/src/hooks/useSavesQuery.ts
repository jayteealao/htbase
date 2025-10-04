import { useQuery } from '@tanstack/react-query'
import { getSaves } from '../api/saves'
import type { SaveRecord } from '../api/types'

export function useSavesQuery(limit = 200) {
  return useQuery<SaveRecord[], Error>({
    queryKey: ['saves', { limit }],
    queryFn: () => getSaves({ limit }),
    staleTime: 30_000,
  })
}

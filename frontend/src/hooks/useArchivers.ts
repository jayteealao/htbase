import { useQuery } from '@tanstack/react-query'
import { getArchivers } from '../api/saves'

export function useArchiversQuery() {
  return useQuery<string[], Error>({
    queryKey: ['archivers'],
    queryFn: getArchivers,
    staleTime: 60_000,
  })
}

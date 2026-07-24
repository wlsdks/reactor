import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '../../shared/lib/queryKeys'
import { getErrorMessage } from '../../shared/lib/getErrorMessage'
import { STALE_TIMES } from '../../shared/lib/staleTimes'
import { getDashboard } from '../dashboard/api'

export function useReleaseOperationsData() {
  const query = useQuery({
    queryKey: queryKeys.dashboard.main(),
    queryFn: () => getDashboard(),
    select: (dashboard) => dashboard.releaseReadiness ?? null,
    staleTime: STALE_TIMES.STANDARD,
    throwOnError: false,
  })

  return {
    readiness: query.data ?? null,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    error: query.error ? getErrorMessage(query.error) : null,
    refetch: query.refetch,
  }
}

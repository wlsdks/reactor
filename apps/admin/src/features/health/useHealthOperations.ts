import { useMutation, useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { getDoctorReport } from '../doctor/api'
import {
  evaluateAlerts,
  getPlatformHealth,
  invalidateResponseCache,
} from '../platform-admin/api'
import { queryKeys } from '../../shared/lib/queryKeys'
import { useToastStore } from '../../shared/store/toast.store'

export function useHealthOperations() {
  const { t } = useTranslation()
  const doctorQuery = useQuery({
    queryKey: queryKeys.doctor.report(),
    queryFn: getDoctorReport,
    refetchInterval: 120_000,
    refetchIntervalInBackground: false,
  })
  const platformQuery = useQuery({
    queryKey: queryKeys.platformAdmin.health(),
    queryFn: getPlatformHealth,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  })

  const evaluateMutation = useMutation({
    mutationFn: evaluateAlerts,
    onSuccess: async () => {
      await platformQuery.refetch()
      useToastStore.getState().addToast({ type: 'success', message: t('platformAdminPage.evaluateAlertsSuccess') })
    },
  })
  const cacheMutation = useMutation({
    mutationFn: invalidateResponseCache,
    onSuccess: async (result) => {
      await platformQuery.refetch()
      useToastStore.getState().addToast({ type: 'success', message: result.message })
    },
  })

  const refresh = async () => {
    await Promise.all([doctorQuery.refetch(), platformQuery.refetch()])
  }

  return {
    doctorQuery,
    platformQuery,
    refresh,
    evaluateAlerts: () => evaluateMutation.mutate(),
    invalidateCache: () => cacheMutation.mutate(),
    actionPending: evaluateMutation.isPending || cacheMutation.isPending,
    actionError: evaluateMutation.error ?? cacheMutation.error,
  }
}

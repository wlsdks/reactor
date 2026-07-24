import type {
  ScheduledJobResponse,
  CreateScheduledJobRequest,
  ScheduledJobExecutionResponse,
} from './types'
import { api } from '../../shared/api/client'

export const listJobs = async (): Promise<ScheduledJobResponse[]> => {
  const data = await api.get('scheduler/jobs', { searchParams: { limit: 200 } }).json<{ items: ScheduledJobResponse[] } | ScheduledJobResponse[]>()
  return Array.isArray(data) ? data : data.items
}

export const getJob = (id: string): Promise<ScheduledJobResponse> =>
  api.get(`scheduler/jobs/${id}`).json()

export const createJob = (request: CreateScheduledJobRequest): Promise<ScheduledJobResponse> =>
  api.post('scheduler/jobs', { json: request }).json()

export const updateJob = (id: string, request: CreateScheduledJobRequest): Promise<ScheduledJobResponse> =>
  api.put(`scheduler/jobs/${id}`, { json: request }).json()

export const deleteJob = (id: string): Promise<void> =>
  api.delete(`scheduler/jobs/${id}`).then(() => undefined)

export const triggerJob = async (id: string): Promise<string> => {
  const data = await api.post(`scheduler/jobs/${id}/trigger`).json<{ result: string }>()
  return data.result
}

export const dryRunJob = async (id: string): Promise<string> => {
  const data = await api.post(`scheduler/jobs/${id}/dry-run`).json<{ result: string }>()
  return data.result
}

export const getExecutions = async (id: string, limit = 100): Promise<ScheduledJobExecutionResponse[]> => {
  const data = await api
    .get(`scheduler/jobs/${id}/executions`, { searchParams: { limit: String(limit), pageLimit: String(limit) } })
    .json<{ items: ScheduledJobExecutionResponse[] } | ScheduledJobExecutionResponse[]>()
  return Array.isArray(data) ? data : data.items
}

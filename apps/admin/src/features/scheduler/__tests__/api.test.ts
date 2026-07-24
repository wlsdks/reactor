import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  listJobs,
  getJob,
  createJob,
  updateJob,
  deleteJob,
  triggerJob,
  dryRunJob,
  getExecutions,
} from '../api'

const mockApiGet = vi.fn()
const mockApiPost = vi.fn()
const mockApiPut = vi.fn()
const mockApiDelete = vi.fn()

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockApiGet(...args),
    post: (...args: unknown[]) => mockApiPost(...args),
    put: (...args: unknown[]) => mockApiPut(...args),
    delete: (...args: unknown[]) => mockApiDelete(...args),
  },
  getAuthToken: vi.fn(() => null),
  setAuthToken: vi.fn(),
  removeAuthToken: vi.fn(),
  setOnUnauthorized: vi.fn(),
}))

function jsonResponse(data: unknown) {
  return { json: () => Promise.resolve(data) }
}

function thenResponse() {
  return { then: (callback: (value: unknown) => unknown) => Promise.resolve(callback(undefined)) }
}

const mockJob = {
  id: 'job-1',
  name: 'daily-cleanup',
  cron: '0 0 * * *',
  enabled: true,
  action: 'cleanup',
  createdAt: '2026-03-01T00:00:00Z',
}

describe('scheduler api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('listJobs returns array of jobs', async () => {
    mockApiGet.mockReturnValue(jsonResponse([mockJob]))

    const result = await listJobs()

    expect(mockApiGet).toHaveBeenCalledWith('scheduler/jobs', { searchParams: { limit: 200 } })
    expect(Array.isArray(result)).toBe(true)
    expect(result[0].id).toBe('job-1')
  })

  it('getJob returns single job by id', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockJob))

    const result = await getJob('job-1')

    expect(mockApiGet).toHaveBeenCalledWith('scheduler/jobs/job-1')
    expect(result.name).toBe('daily-cleanup')
  })

  it('createJob sends POST and returns created job', async () => {
    mockApiPost.mockReturnValue(jsonResponse(mockJob))

    const result = await createJob({
      name: 'daily-cleanup',
      cron: '0 0 * * *',
      action: 'cleanup',
    })

    expect(mockApiPost).toHaveBeenCalledWith(
      'scheduler/jobs',
      expect.objectContaining({ json: expect.objectContaining({ name: 'daily-cleanup' }) }),
    )
    expect(result.id).toBe('job-1')
  })

  it('updateJob sends PUT and returns updated job', async () => {
    const updated = { ...mockJob, cron: '0 12 * * *' }
    mockApiPut.mockReturnValue(jsonResponse(updated))

    const result = await updateJob('job-1', { ...mockJob, cron: '0 12 * * *' })

    expect(mockApiPut).toHaveBeenCalledWith(
      'scheduler/jobs/job-1',
      expect.objectContaining({ json: expect.objectContaining({ cron: '0 12 * * *' }) }),
    )
    expect(result.cron).toBe('0 12 * * *')
  })

  it('deleteJob sends DELETE without error', async () => {
    mockApiDelete.mockReturnValue(thenResponse())

    await expect(deleteJob('job-1')).resolves.not.toThrow()

    expect(mockApiDelete).toHaveBeenCalledWith('scheduler/jobs/job-1')
  })

  it('triggerJob sends POST and returns result string', async () => {
    mockApiPost.mockReturnValue(jsonResponse({ result: 'Job triggered successfully' }))

    const result = await triggerJob('job-1')

    expect(mockApiPost).toHaveBeenCalledWith('scheduler/jobs/job-1/trigger')
    expect(result).toBe('Job triggered successfully')
  })

  it('dryRunJob sends POST and returns dry-run result string', async () => {
    mockApiPost.mockReturnValue(jsonResponse({ result: 'Dry run completed: 5 items would be cleaned' }))

    const result = await dryRunJob('job-1')

    expect(mockApiPost).toHaveBeenCalledWith('scheduler/jobs/job-1/dry-run')
    expect(result).toContain('Dry run completed')
  })

  it('getExecutions unwraps the backend paginated response', async () => {
    const mockExecutions = [
      { id: 'exec-1', jobId: 'job-1', status: 'success', startedAt: '2026-03-01T00:00:00Z' },
    ]
    mockApiGet.mockReturnValue(jsonResponse({ items: mockExecutions, total: 1, offset: 0, limit: 100 }))

    const result = await getExecutions('job-1')

    expect(mockApiGet).toHaveBeenCalledWith(
      'scheduler/jobs/job-1/executions',
      expect.objectContaining({ searchParams: { limit: '100', pageLimit: '100' } }),
    )
    expect(Array.isArray(result)).toBe(true)
    expect(result[0].id).toBe('exec-1')
  })

  it('getExecutions passes custom limit', async () => {
    mockApiGet.mockReturnValue(jsonResponse([]))

    await getExecutions('job-1', 50)

    expect(mockApiGet).toHaveBeenCalledWith(
      'scheduler/jobs/job-1/executions',
      expect.objectContaining({ searchParams: { limit: '50', pageLimit: '50' } }),
    )
  })
})

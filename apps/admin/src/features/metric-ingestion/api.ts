import { api } from '../../shared/api/client'
import type {
  EvalResultRequest,
  EvalRunResultsRequest,
  McpHealthRequest,
  ToolCallRequest,
} from './types'

export const ingestMcpHealth = (request: McpHealthRequest): Promise<Record<string, unknown>> =>
  api.post('admin/metrics/ingest/mcp-health', { json: request }).json()

export const ingestToolCall = (request: ToolCallRequest): Promise<Record<string, unknown>> =>
  api.post('admin/metrics/ingest/tool-call', { json: request }).json()

export const ingestEvalResult = (request: EvalResultRequest): Promise<Record<string, unknown>> =>
  api.post('admin/metrics/ingest/eval-result', { json: request }).json()

export const ingestEvalResults = (request: EvalRunResultsRequest): Promise<Record<string, unknown>> =>
  api.post('admin/metrics/ingest/eval-results', { json: request }).json()

export const ingestMcpHealthBatch = (requests: McpHealthRequest[]): Promise<Record<string, unknown>> =>
  api.post('admin/metrics/ingest/batch', { json: requests }).json()

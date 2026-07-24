import { api } from '../../shared/api/client'
import type { DebugReplayCapture } from './types'

/**
 * R538: 실패 요청 캡처 목록 조회 (테넌트별).
 */
export const listDebugReplayCaptures = async (
  tenantId: string = 'default',
  limit: number = 50
): Promise<DebugReplayCapture[]> => {
  const data = await api
    .get('admin/debug/replay', { searchParams: { tenantId, limit } })
    .json<DebugReplayCapture[] | { items: DebugReplayCapture[] }>()
  return Array.isArray(data) ? data : data.items
}

/**
 * R538: 특정 캡처 단건 조회.
 */
export const getDebugReplayCapture = (id: string): Promise<DebugReplayCapture> =>
  api.get(`admin/debug/replay/${id}`).json()

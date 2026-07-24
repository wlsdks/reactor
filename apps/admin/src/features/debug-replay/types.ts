/**
 * R538: Debug Replay 캡처 DTO (backend: DebugReplayCapture).
 * 실패한 요청의 원문을 저장하여 개발자가 동일 입력으로 재현할 수 있도록 한다.
 */
export interface DebugReplayCapture {
  id: string
  tenantId: string
  userHash: string | null
  capturedAt: string
  userPrompt: string
  errorCode: string | null
  errorMessage: string | null
  modelId: string | null
  toolsAttempted: string | null
  expiresAt: string
}

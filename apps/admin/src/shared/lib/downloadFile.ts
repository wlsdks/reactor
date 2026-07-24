/**
 * Blob 데이터를 클라이언트측에서 파일로 다운로드한다.
 *
 * 기존 `document.body.appendChild(anchor).click().removeChild()` 패턴은 React
 * 컴포넌트 밖에서 DOM 을 직접 조작해 테스트/SSR 에 부담이 있고, React strict
 * mode 에서 race 여지도 있음. 최신 브라우저(Chrome/Firefox/Safari 15+/Edge)
 * 는 anchor 를 DOM 에 mount 하지 않아도 `click()` 이 동작하므로 mount 단계를
 * 제거.
 *
 * URL object 는 호출 직후 `revokeObjectURL` 로 해제 — 비동기 click 경로를
 * 고려해 `queueMicrotask` 로 revoke 를 한 틱 뒤로 미룸.
 *
 * @param data JSON string / Blob-compatible payload
 * @param filename 브라우저에 제안할 파일명 (예: `feedback-2026-04-17.json`)
 * @param mimeType 기본 application/json
 */
export function downloadFile(
  data: BlobPart,
  filename: string,
  mimeType: string = 'application/json',
): void {
  const blob = data instanceof Blob ? data : new Blob([data], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.rel = 'noopener'
  anchor.click()
  queueMicrotask(() => URL.revokeObjectURL(url))
}

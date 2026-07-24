import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import {
  List,
  useDynamicRowHeight,
  useListRef,
  type RowComponentProps,
} from 'react-window'
import type { ChatMessage } from '../../types'
import type { MessageCost } from '../../../token-cost/types'
import { ChatBubble } from './ChatBubble'

/**
 * Threshold (number of rows from the start of the rendered slice) at which we
 * trigger loading the next older batch. Once the user scrolls the virtualised
 * list close enough to the top we ask the parent to extend the visible window.
 *
 * NOTE: Although the task brief mentions "near bottom", the chat data model in
 * SessionDetail renders the *latest* N messages (slice from the end). Older
 * messages are therefore at the top of the visible slice, so the
 * lazy-load-more trigger for this feature fires when the user scrolls near
 * the top. This preserves the existing cursor-based pagination semantics.
 */
const NEAR_EDGE_ROW_THRESHOLD = 4

/** Reasonable default height for a message bubble before measurement. */
const DEFAULT_ROW_HEIGHT = 96

interface MessageListProps {
  /**
   * Ordered list of chat messages (oldest at index 0, newest at the end).
   * Already sliced by the caller to the currently visible window.
   */
  messages: ChatMessage[]
  /** Map from message.id to its token cost, if available. */
  costsByMessageIndex: Map<number, MessageCost>
  showCost: boolean
  /**
   * True when more messages exist beyond the currently visible slice and can
   * be lazily loaded by calling {@link onLoadOlder}.
   */
  hasOlderMessages: boolean
  /**
   * Called when the user scrolls near the top of the virtualised list while
   * {@link hasOlderMessages} is true. Should extend the visible window by one
   * batch.
   */
  onLoadOlder: () => void
}

interface RowExtraProps {
  messages: ChatMessage[]
  costsByMessageIndex: Map<number, MessageCost>
  showCost: boolean
}

function MessageRow({
  index,
  style,
  messages,
  costsByMessageIndex,
  showCost,
}: RowComponentProps<RowExtraProps>) {
  const msg = messages[index]
  if (!msg) return null
  return (
    <div style={style} className="virtualized-row" data-testid="virtualized-row">
      <ChatBubble
        message={msg}
        cost={costsByMessageIndex.get(msg.id)}
        showCost={showCost}
      />
    </div>
  )
}

export function MessageList({
  messages,
  costsByMessageIndex,
  showCost,
  hasOlderMessages,
  onLoadOlder,
}: MessageListProps) {
  const { t } = useTranslation()
  // Guard against repeatedly invoking onLoadOlder while the user lingers near
  // the top edge. We reset this flag whenever the visible range moves away
  // from the threshold.
  const loadPendingRef = useRef(false)
  // `hasScrolledRef` is toggled the first time the list reports a visible
  // window that is not anchored to the very top. This prevents auto-loading
  // on initial mount (where startIndex is naturally 0).
  const hasScrolledRef = useRef(false)
  const listRef = useListRef(null)

  const rowHeight = useDynamicRowHeight({ defaultRowHeight: DEFAULT_ROW_HEIGHT })

  const rowCount = messages.length
  const hasCompactConversation = rowCount <= 3

  // Anchor the list to the newest message the first time we have rows. After
  // that we leave scroll position alone so lazy-loading older messages does
  // not yank the viewport. This also moves the reported `startIndex` away
  // from 0, so the near-top auto-load guard works correctly on user scroll.
  const initialScrollAppliedRef = useRef(false)
  useEffect(() => {
    if (initialScrollAppliedRef.current || rowCount === 0) return
    initialScrollAppliedRef.current = true
    listRef.current?.scrollToRow({ index: rowCount - 1, align: 'end', behavior: 'instant' })
  }, [rowCount, listRef])

  return (
    <div
      className="chat-area chat-area--virtualized"
      role="log"
      aria-live="polite"
      aria-relevant="additions text"
      aria-label={t('conversations.detail.title')}
      data-testid="message-list-virtualized"
    >
      <List
        listRef={listRef}
        className="message-list"
        rowCount={rowCount}
        rowHeight={rowHeight}
        rowComponent={MessageRow}
        rowProps={{ messages, costsByMessageIndex, showCost }}
        overscanCount={4}
        defaultHeight={600}
        style={{
          height: hasCompactConversation
            ? 'var(--conversation-list-compact-height)'
            : 'min(var(--conversation-list-max-height), calc(100vh - var(--conversation-list-viewport-offset)))',
        }}
        onRowsRendered={(visibleRows) => {
          // Record the first non-initial scroll so we don't auto-trigger on
          // mount. The initial render naturally reports startIndex = 0.
          if (!hasScrolledRef.current && visibleRows.startIndex > 0) {
            hasScrolledRef.current = true
          }

          const nearTop = visibleRows.startIndex <= NEAR_EDGE_ROW_THRESHOLD
          if (
            nearTop &&
            hasOlderMessages &&
            hasScrolledRef.current &&
            !loadPendingRef.current
          ) {
            loadPendingRef.current = true
            onLoadOlder()
          } else if (!nearTop) {
            loadPendingRef.current = false
          }
        }}
      />
      <div className="session-chat-end-marker">
        {t('conversations.detail.endOfConversation')}
      </div>
    </div>
  )
}

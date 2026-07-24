import { RELEASE_FEEDBACK_PROMOTION_ANCHOR_ID } from '../../shared/releaseWorkflow'

export const FEEDBACK_PROMOTION_ANCHORS = {
  panelId: RELEASE_FEEDBACK_PROMOTION_ANCHOR_ID,
  releaseEvidenceId: 'feedback-release-evidence',
  panelHref: `#${RELEASE_FEEDBACK_PROMOTION_ANCHOR_ID}`,
  releaseEvidenceHref: '#feedback-release-evidence',
} as const

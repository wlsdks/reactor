import type { Channel } from '../../types'
import { Braces, CircleHelp, Gamepad2, Globe2, MessageCircle, UsersRound, type LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Tooltip } from '../../../../shared/ui'

const CHANNEL_ICONS: Record<Channel, LucideIcon> = {
  web: Globe2,
  slack: MessageCircle,
  teams: UsersRound,
  discord: Gamepad2,
  api: Braces,
  unknown: CircleHelp,
}

interface ChannelIconProps {
  channel: Channel
}

export function ChannelIcon({ channel }: ChannelIconProps) {
  const { t } = useTranslation()
  const Icon = CHANNEL_ICONS[channel]
  const label = t(`conversations.channels.${channel}`)

  return (
    <Tooltip content={label}>
      <span className="channel-icon" aria-label={label}>
        <Icon aria-hidden="true" className="channel-icon__glyph" strokeWidth={1.8} />
      </span>
    </Tooltip>
  )
}

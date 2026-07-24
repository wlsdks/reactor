/**
 * Allowlist of legacy `/platform-admin?tab=...` values mapped to their
 * destination URL in the new navigation structure. Unknown tabs fall back
 * to `/tenants`. The map is intentionally hardcoded — never derive the
 * destination from user input by string concatenation.
 */
const TAB_DESTINATIONS: Record<string, string> = {
  health: '/health',
  tenants: '/tenants',
  pricing: '/models?tab=pricing',
  roles: '/access-control?tab=members',
  retention: '/settings?tab=retention',
  settings: '/settings',
  tenant: '/tenants?tab=tenant',
}

const FALLBACK_DESTINATION = '/tenants'

export interface RedirectResolution {
  destination: string
  destinationLabel: string
  isFallback: boolean
}

export function resolveRedirectDestination(tab: string | null): RedirectResolution {
  if (tab && tab in TAB_DESTINATIONS) {
    return {
      destination: TAB_DESTINATIONS[tab],
      destinationLabel: humanLabelForTab(tab),
      isFallback: false,
    }
  }
  return {
    destination: FALLBACK_DESTINATION,
    destinationLabel: humanLabelForTab('tenants'),
    isFallback: true,
  }
}

function humanLabelForTab(tab: string): string {
  switch (tab) {
    case 'health':
      return 'Health'
    case 'tenants':
    case 'tenant':
      return 'Tenants'
    case 'pricing':
      return 'Models · Pricing'
    case 'roles':
      return 'Access Control · Members'
    case 'retention':
      return 'Retention'
    case 'settings':
      return 'Settings'
    default:
      return 'Tenants'
  }
}

/**
 * Append any unrelated query params from the source URL onto the destination,
 * so that filters or deep-link state are preserved across the redirect.
 * The `tab` param itself is dropped because the destination already encodes it.
 */
export function buildPreservedDestination(
  destination: string,
  sourceParams: URLSearchParams,
): string {
  const [path, existingQuery = ''] = destination.split('?')
  const merged = new URLSearchParams(existingQuery)
  for (const [key, value] of sourceParams.entries()) {
    if (key === 'tab') continue
    if (!merged.has(key)) merged.set(key, value)
  }
  const queryString = merged.toString()
  return queryString ? `${path}?${queryString}` : path
}

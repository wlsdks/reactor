import { api } from '../../shared/api/client'

export interface CapabilityManifestResponse {
  generatedAt: number
  source: string
  durable: boolean
  paths: string[]
}

export interface CapabilityManifest extends Set<string> {
  durable: boolean
}

export async function getCapabilityManifest(): Promise<CapabilityManifest | null> {
  try {
    const data = await api.get('admin/capabilities').json<Partial<CapabilityManifestResponse>>()
    if (!Array.isArray(data.paths)) return null
    const manifest = new Set(
      data.paths.filter((path): path is string => typeof path === 'string' && path.length > 0),
    ) as CapabilityManifest
    // Older compatible backends did not expose runtime durability. Treat an
    // absent field as durable so capability discovery remains fail-compatible.
    manifest.durable = data.durable !== false
    return manifest
  } catch {
    return null
  }
}

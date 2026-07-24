import { create } from 'zustand'
import { paletteColor } from '../../shared/ui/ChartConfig'
import { STORAGE_KEYS, safeGetJson, safeSetJson } from '../../shared/lib/safeLocalStorage'

// Tag-key → palette color. Mirrors role pill convention so users see a
// consistent color story for "category meaning" across the admin UI.
//   env  → 0 (blue)    | team → 1 (emerald)
//   type → 2 (amber, categorical distinction)
//   default → 7 (slate / neutral)
const TAG_KEY_COLORS: Record<string, string> = {
  env: paletteColor(0),
  team: paletteColor(1),
  type: paletteColor(2),
}
const DEFAULT_TAG_COLOR = paletteColor(7)

function loadFromStorage(): Record<string, string[]> {
  const parsed = safeGetJson<Record<string, string[]>>(STORAGE_KEYS.mcpServerTags, {})
  return parsed ?? {}
}

function saveToStorage(tags: Record<string, string[]>): void {
  safeSetJson(STORAGE_KEYS.mcpServerTags, tags)
}

interface TagStore {
  tags: Record<string, string[]>
  setTags: (serverName: string, tags: string[]) => void
  removeTags: (serverName: string) => void
  getAllUniqueTags: () => string[]
  getTagColor: (tag: string) => string
}

export const useTagStore = create<TagStore>((set, get) => ({
  tags: loadFromStorage(),

  setTags: (serverName, newTags) => {
    set((state) => {
      const updated = { ...state.tags, [serverName]: newTags }
      saveToStorage(updated)
      return { tags: updated }
    })
  },

  removeTags: (serverName) => {
    set((state) => {
      const rest = Object.fromEntries(
        Object.entries(state.tags).filter(([key]) => key !== serverName),
      )
      saveToStorage(rest)
      return { tags: rest }
    })
  },

  getAllUniqueTags: () => {
    const all = Object.values(get().tags).flat()
    return [...new Set(all)].sort()
  },

  getTagColor: (tag) => {
    const key = tag.split(':')[0]
    return TAG_KEY_COLORS[key] ?? DEFAULT_TAG_COLOR
  },
}))

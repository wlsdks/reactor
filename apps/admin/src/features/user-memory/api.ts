import type { UserMemory } from './types'
import { api } from '../../shared/api/client'

export const getUserMemory = (userId: string): Promise<UserMemory> =>
  api.get(`user-memory/${userId}`).json()

export const updateUserFacts = (userId: string, facts: Record<string, string>): Promise<void> =>
  api.put(`user-memory/${userId}/facts`, { json: facts }).then(() => undefined)

export const updateUserPreferences = (userId: string, preferences: Record<string, string>): Promise<void> =>
  api.put(`user-memory/${userId}/preferences`, { json: preferences }).then(() => undefined)

export const deleteUserMemory = (userId: string): Promise<void> =>
  api.delete(`user-memory/${userId}`).then(() => undefined)

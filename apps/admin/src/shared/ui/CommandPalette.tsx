import './CommandPalette.css'
import { useState, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useBodyOverflowLock } from '../lib/useBodyOverflowLock'
import { useEscapeKey } from '../lib/useEscapeKey'
import { useRoleVisibility } from '../../features/workspace'
import type { NavGroup, NavItem } from '../types/navigation'
import {
  buildCommandActions,
  filterActionsByQuery,
  filterAvailableActions,
  type CommandAction,
  type CommandActionSection,
} from './commandPaletteActions'
import { searchRecords, type SearchableRecord, type SearchScope } from '../lib/searchIndex'
import { useGlobalSearchRecords } from '../lib/useGlobalSearchRecords'
import { EmptyState } from './EmptyState'

interface NavEntry {
  kind: 'nav'
  group: string
  groupDescription: string
  item: NavItem
  /** Used as React key + for keyboard navigation. */
  key: string
}

interface ActionEntry {
  kind: 'action'
  section: CommandActionSection
  action: CommandAction
  key: string
}

interface SearchEntry {
  kind: 'search'
  record: SearchableRecord
  key: string
}

type Entry = NavEntry | ActionEntry | SearchEntry

const SEARCH_RESULT_LIMIT = 20

const SEARCH_SCOPE_KEYS: Record<SearchScope, string> = {
  release: 'commandPalette.search.scope.release',
  persona: 'commandPalette.search.scope.persona',
  prompt: 'commandPalette.search.scope.prompt',
  feedback: 'commandPalette.search.scope.feedback',
  audit: 'commandPalette.search.scope.audit',
  session: 'commandPalette.search.scope.session',
}

interface CommandPaletteProps {
  navGroups: NavGroup[]
}

const SECTION_ORDER: CommandActionSection[] = ['release', 'navigate', 'create', 'action']

const SECTION_TITLE_KEYS: Record<CommandActionSection, string> = {
  release: 'commandPalette.sections.release',
  navigate: 'commandPalette.sections.navigate',
  create: 'commandPalette.sections.create',
  action: 'commandPalette.sections.action',
}

function flattenNavGroups(groups: NavGroup[], t: (key: string) => string): NavEntry[] {
  const result: NavEntry[] = []
  for (const group of groups) {
    const groupDescription = group.descriptionKey ? t(group.descriptionKey) : ''
    for (const item of group.items) {
      result.push({
        kind: 'nav',
        group: t(group.titleKey),
        groupDescription,
        item,
        key: `nav:${item.path}`,
      })
    }
  }
  return result
}

function filterNavEntries(
  entries: NavEntry[],
  query: string,
  t: (key: string) => string,
): NavEntry[] {
  const trimmed = query.trim().toLowerCase()
  if (!trimmed) return entries
  return entries.filter(({ group, groupDescription, item }) => {
    const label = t(item.label).toLowerCase()
    const desc = t(item.description).toLowerCase()
    const terms = [group.toLowerCase(), groupDescription.toLowerCase(), label, desc]
    if (item.releaseStepNumber) {
      const step = item.releaseStepNumber
      terms.push(
        `${step}`,
        `step ${step}`,
        `release step ${step}`,
        `workflow step ${step}`,
        `${step}단계`,
        `단계 ${step}`,
        `릴리즈 단계 ${step}`,
        `릴리즈 흐름 ${step}단계`,
      )
    }
    return terms.some((term) => term.includes(trimmed))
  })
}

function describeNavEntry(entry: NavEntry, t: (key: string) => string): string {
  const itemDescription = t(entry.item.description)
  if (!entry.item.releaseStepNumber || !entry.groupDescription) return itemDescription
  return `${entry.group} · ${itemDescription}`
}

interface RenderableSection {
  /** Localised section header label. */
  title: string
  entries: Entry[]
}

function buildRenderableSections(
  navEntries: NavEntry[],
  actions: CommandAction[],
  searchEntries: SearchEntry[],
  t: (key: string) => string,
): RenderableSection[] {
  const sections: RenderableSection[] = []
  for (const sectionKey of SECTION_ORDER) {
    const sectionActions = actions
      .filter((a) => a.section === sectionKey)
      .map<ActionEntry>((action) => ({
        kind: 'action',
        section: sectionKey,
        action,
        key: `action:${action.id}`,
      }))
    const entries: Entry[] = sectionKey === 'navigate'
      ? [...navEntries, ...sectionActions]
      : sectionActions
    if (entries.length === 0) continue
    sections.push({
      title: t(SECTION_TITLE_KEYS[sectionKey]),
      entries,
    })
  }
  // Data search results render after the static sections so static actions
  // remain instantly accessible at the top of the list.
  if (searchEntries.length > 0) {
    sections.push({
      title: t('commandPalette.search.sectionTitle'),
      entries: searchEntries,
    })
  }
  return sections
}

export function CommandPalette({ navGroups }: CommandPaletteProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { effectiveRole, canToggleViewAs, toggleViewAsManager, isRouteVisible } = useRoleVisibility()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  useBodyOverflowLock(open)
  useEscapeKey(open, () => setOpen(false))

  function closePalette() {
    setOpen(false)
  }

  // Global Cmd+K / Ctrl+K listener
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen(prev => {
          if (!prev) {
            // Opening: reset state
            setQuery('')
            setSelectedIndex(0)
          }
          return !prev
        })
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Listen for an explicit "open" event so non-keyboard surfaces (header
  // trigger, onboarding tour, etc.) can open the palette without each
  // duplicating the toggle logic.
  useEffect(() => {
    function handleOpen() {
      setOpen(true)
      setQuery('')
      setSelectedIndex(0)
    }
    document.addEventListener('cmd-palette:open', handleOpen)
    return () => document.removeEventListener('cmd-palette:open', handleOpen)
  }, [])

  // Auto-focus input when opened
  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => {
        inputRef.current?.focus()
      })
    }
  }, [open])

  const navEntriesAll = flattenNavGroups(navGroups, t)
  const filteredNavEntries = filterNavEntries(navEntriesAll, query, t)
  const allActions = filterAvailableActions(
    buildCommandActions({
      navigate,
      role: effectiveRole,
      toggleViewAsManager,
      canToggleViewAs,
    }),
  )
  const filteredActions = filterActionsByQuery(allActions, query, t)

  // Data search runs only when the user has typed a query — otherwise the
  // palette stays focused on the static nav / action menu.
  const allSearchRecords = useGlobalSearchRecords()
  const visibleSearchRecords = allSearchRecords.filter((record) => isRouteVisible(record.navigateTo))
  const searchEntries: SearchEntry[] = query.trim()
    ? searchRecords(query, visibleSearchRecords, SEARCH_RESULT_LIMIT).map<SearchEntry>((record) => ({
        kind: 'search',
        record,
        key: `search:${record.scope}:${record.id}`,
      }))
    : []

  const sections = buildRenderableSections(filteredNavEntries, filteredActions, searchEntries, t)
  const flatEntries: Entry[] = sections.flatMap((s) => s.entries)
  const totalCount = flatEntries.length

  function handleQueryChange(e: React.ChangeEvent<HTMLInputElement>) {
    setQuery(e.target.value)
    setSelectedIndex(0)
  }

  // Scroll selected item into view
  useEffect(() => {
    if (!listRef.current) return
    const selectedEl = listRef.current.querySelector('.cmd-palette__item--selected')
    if (selectedEl) {
      selectedEl.scrollIntoView?.({ block: 'nearest' })
    }
  }, [selectedIndex])

  function runEntry(entry: Entry) {
    closePalette()
    if (entry.kind === 'nav') {
      navigate(entry.item.path)
    } else if (entry.kind === 'action') {
      entry.action.perform()
    } else {
      navigate(entry.record.navigateTo)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (totalCount === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIndex(prev => (prev + 1) % totalCount)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIndex(prev => (prev - 1 + totalCount) % totalCount)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const selected = flatEntries[selectedIndex]
      if (selected) runEntry(selected)
    }
  }

  if (!open) return null

  let runningIndex = 0

  return createPortal(
    <div className="cmd-palette-overlay" onClick={closePalette}>
      <div
        className="cmd-palette"
        role="dialog"
        aria-modal="true"
        aria-label={t('common.commandPalette.placeholder')}
        onClick={e => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <input
          ref={inputRef}
          className="cmd-palette__input"
          type="text"
          placeholder={t('common.commandPalette.placeholder')}
          value={query}
          onChange={handleQueryChange}
          aria-label={t('common.commandPalette.placeholder')}
        />
        <div className="cmd-palette__divider" />
        <div className="cmd-palette__list" ref={listRef} role="listbox">
          {totalCount === 0 ? (
            <div className="cmd-palette__empty">
              {query.trim() ? (
                <EmptyState
                  filtered
                  message={t('commandPalette.search.emptyResult')}
                  filterSummary={query.trim()}
                  onClearFilters={() => {
                    setQuery('')
                    setSelectedIndex(0)
                    requestAnimationFrame(() => inputRef.current?.focus())
                  }}
                />
              ) : (
                t('common.commandPalette.empty')
              )}
            </div>
          ) : (
            sections.map((section) => (
              <div key={section.title} data-section={section.title}>
                <div className="cmd-palette__group">{section.title}</div>
                {section.entries.map((entry) => {
                  const index = runningIndex++
                  const isSelected = index === selectedIndex
                  if (entry.kind === 'nav') {
                    const IconComponent = entry.item.icon
                    const navLabel = entry.item.releaseStepNumber
                      ? `${entry.item.releaseStepNumber}. ${t(entry.item.label)}`
                      : undefined
                    return (
                      <div
                        key={entry.key}
                        className={`cmd-palette__item${isSelected ? ' cmd-palette__item--selected' : ''}`}
                        role="option"
                        aria-selected={isSelected}
                        aria-label={navLabel}
                        onClick={() => runEntry(entry)}
                        onMouseEnter={() => setSelectedIndex(index)}
                      >
                        <span className="cmd-palette__item-icon">
                          <IconComponent size={16} strokeWidth={1.5} />
                        </span>
                        <div className="cmd-palette__item-text">
                          <span className="cmd-palette__item-label">
                            {entry.item.releaseStepNumber ? (
                              <span className="cmd-palette__step" aria-hidden="true">
                                {entry.item.releaseStepNumber}
                              </span>
                            ) : null}
                            {t(entry.item.label)}
                          </span>
                          <span className="cmd-palette__item-desc">
                            {describeNavEntry(entry, t)}
                          </span>
                        </div>
                      </div>
                    )
                  }
                  if (entry.kind === 'action') {
                    const actionLabel = entry.action.stepNumber
                      ? `${entry.action.stepNumber}. ${t(entry.action.titleKey)}`
                      : t(entry.action.titleKey)
                    return (
                      <div
                        key={entry.key}
                        className={`cmd-palette__item${isSelected ? ' cmd-palette__item--selected' : ''}`}
                        role="option"
                        aria-selected={isSelected}
                        aria-label={actionLabel}
                        data-action-id={entry.action.id}
                        onClick={() => runEntry(entry)}
                        onMouseEnter={() => setSelectedIndex(index)}
                      >
                        <span className="cmd-palette__item-icon" aria-hidden="true">
                          <span className="cmd-palette__action-glyph" />
                        </span>
                        <div className="cmd-palette__item-text">
                          <span className="cmd-palette__item-label">
                            {entry.action.stepNumber ? (
                              <span className="cmd-palette__step" aria-hidden="true">
                                {entry.action.stepNumber}
                              </span>
                            ) : null}
                            {t(entry.action.titleKey)}
                          </span>
                          {entry.action.descriptionKey ? (
                            <span className="cmd-palette__item-desc">
                              {t(entry.action.descriptionKey)}
                            </span>
                          ) : null}
                        </div>
                      </div>
                    )
                  }
                  // Data search result row.
                  const searchLabel = entry.record.stepNumber
                    ? `${entry.record.stepNumber}. ${entry.record.title}`
                    : entry.record.title
                  return (
                    <div
                      key={entry.key}
                      className={`cmd-palette__item${isSelected ? ' cmd-palette__item--selected' : ''}`}
                      role="option"
                      aria-selected={isSelected}
                      aria-label={searchLabel}
                      data-search-scope={entry.record.scope}
                      data-search-id={entry.record.id}
                      onClick={() => runEntry(entry)}
                      onMouseEnter={() => setSelectedIndex(index)}
                    >
                      <span
                        className={`cmd-palette__scope-chip cmd-palette__scope-chip--${entry.record.scope}`}
                        aria-hidden="true"
                      >
                        {t(SEARCH_SCOPE_KEYS[entry.record.scope])}
                      </span>
                      <div className="cmd-palette__item-text">
                        <span className="cmd-palette__item-label">
                          {entry.record.stepNumber ? (
                            <span className="cmd-palette__step" aria-hidden="true">
                              {entry.record.stepNumber}
                            </span>
                          ) : null}
                          {entry.record.title}
                        </span>
                        {entry.record.subtitle ? (
                          <span className="cmd-palette__item-desc">{entry.record.subtitle}</span>
                        ) : null}
                      </div>
                    </div>
                  )
                })}
              </div>
            ))
          )}
        </div>
        <div className="cmd-palette__footer">
          <span className="cmd-palette__footer-item">
            <kbd className="cmd-palette__kbd">&uarr;</kbd>
            <kbd className="cmd-palette__kbd">&darr;</kbd>
            {t('common.commandPalette.navigateHint')}
          </span>
          <span className="cmd-palette__footer-item">
            <kbd className="cmd-palette__kbd">{t('common.enter')}</kbd>
            {t('common.commandPalette.runHint')}
          </span>
          <span className="cmd-palette__footer-item">
            <kbd className="cmd-palette__kbd">Esc</kbd>
            {t('common.commandPalette.close')}
          </span>
        </div>
      </div>
    </div>,
    document.body,
  )
}

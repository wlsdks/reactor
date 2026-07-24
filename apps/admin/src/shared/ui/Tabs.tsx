import { useRef, type KeyboardEvent, type ReactNode } from 'react'
import './Tabs.css'

export interface TabDefinition {
  value: string
  label: ReactNode
  panel: ReactNode
}

export interface TabsProps {
  tabs: TabDefinition[]
  value: string
  onChange: (next: string) => void
  ariaLabel: string
}

export function Tabs({ tabs, value, onChange, ariaLabel }: TabsProps) {
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([])
  const activeIndex = Math.max(0, tabs.findIndex((t) => t.value === value))

  const handleKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    let next = activeIndex
    if (e.key === 'ArrowRight') next = (activeIndex + 1) % tabs.length
    else if (e.key === 'ArrowLeft') next = (activeIndex - 1 + tabs.length) % tabs.length
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = tabs.length - 1
    else return
    e.preventDefault()
    onChange(tabs[next].value)
    tabRefs.current[next]?.focus()
  }

  return (
    <div className="tabs-container">
      <div role="tablist" aria-label={ariaLabel} className="tabs-list">
        {tabs.map((tab, i) => {
          const selected = tab.value === value
          return (
            <button
              key={tab.value}
              ref={(el) => {
                tabRefs.current[i] = el
              }}
              role="tab"
              type="button"
              aria-selected={selected}
              aria-controls={`tabpanel-${tab.value}`}
              id={`tab-${tab.value}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(tab.value)}
              onKeyDown={handleKeyDown}
              className={selected ? 'tabs-tab tabs-tab-active' : 'tabs-tab'}
            >
              {tab.label}
            </button>
          )
        })}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.value}
          role="tabpanel"
          id={`tabpanel-${tab.value}`}
          aria-labelledby={`tab-${tab.value}`}
          hidden={tab.value !== value}
          className="tabs-panel"
        >
          {tab.value === value && tab.panel}
        </div>
      ))}
    </div>
  )
}

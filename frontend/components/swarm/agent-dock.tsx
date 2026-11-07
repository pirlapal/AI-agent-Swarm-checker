"use client"

import * as React from "react"
import { Bot } from "lucide-react"

import { cn } from "@/lib/utils"

import { StatusPill } from "./category-swarm-panel"
import type { CategoryBucket } from "./run-state"

interface AgentCardProps {
  category: CategoryBucket
  selected: boolean
  onSelect: () => void
}

const AgentCard = React.forwardRef<HTMLButtonElement, AgentCardProps>(
  function AgentCard({ category, selected, onSelect }, ref) {
    return (
      <button
        ref={ref}
        type="button"
        role="tab"
        aria-selected={selected}
        onClick={onSelect}
        className={cn(
          "group/agent relative flex w-[220px] shrink-0 snap-start flex-col gap-2 rounded-xl border bg-white/80 p-3 text-left",
          "fade-in-0 slide-in-from-bottom-2 animate-in",
          "transition-all duration-150",
          selected
            ? "border-[#1d1d1f] shadow-depth-2 ring-2 ring-[#1d1d1f]/10"
            : "border-black/[0.08] hover:-translate-y-0.5 hover:border-[#1d1d1f]/30 hover:shadow-depth-1",
        )}
      >
        <div className="flex items-center gap-2">
          <span className="inline-flex size-6 items-center justify-center rounded-full bg-[#1d1d1f]/5">
            <Bot className="size-3 text-[#1d1d1f]" />
          </span>
          <span className="truncate font-mono text-[10px] uppercase tracking-wide text-[#86868b]">
            {category.category_id.slice(0, 6)}
          </span>
          <div className="ml-auto">
            <StatusPill status={category.status} />
          </div>
        </div>
        <div className="line-clamp-2 text-sm font-semibold text-[#1d1d1f]">
          {category.name}
        </div>
        <div className="mt-auto flex items-center gap-3 text-[10px] text-[#86868b]">
          <span>
            <span className="font-medium text-[#1d1d1f]">
              {category.refs.length}
            </span>{" "}
            refs
          </span>
          <span>
            <span className="font-medium text-[#1d1d1f]">
              {category.findings.length}
            </span>{" "}
            findings
          </span>
          <span>
            <span className="font-medium text-[#1d1d1f]">
              {category.toolCalls.length}
            </span>{" "}
            tools
          </span>
        </div>
      </button>
    )
  },
)

interface Props {
  categories: CategoryBucket[]
  selectedCategoryId: string | null
  onSelect: (id: string | null) => void
  className?: string
}

/**
 * Horizontal, scroll-snapping dock of agent cards (one per category).
 * Selecting a card drives what the right-hand AgentPreview shows.
 * Acts as an ARIA tablist for keyboard users.
 */
export function AgentDock({
  categories,
  selectedCategoryId,
  onSelect,
  className,
}: Props) {
  const scrollerRef = React.useRef<HTMLDivElement | null>(null)
  const cardRefs = React.useRef<Map<string, HTMLButtonElement>>(new Map())

  const selectedIndex = Math.max(
    0,
    categories.findIndex((c) => c.category_id === selectedCategoryId),
  )

  const focusIndex = React.useCallback(
    (next: number) => {
      if (categories.length === 0) return
      const wrapped =
        ((next % categories.length) + categories.length) % categories.length
      const target = categories[wrapped]
      onSelect(target.category_id)
      const btn = cardRefs.current.get(target.category_id)
      if (btn) {
        btn.focus({ preventScroll: false })
        btn.scrollIntoView({
          block: "nearest",
          inline: "center",
          behavior: "smooth",
        })
      }
    },
    [categories, onSelect],
  )

  const handleKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowRight") {
      e.preventDefault()
      focusIndex(selectedIndex + 1)
    } else if (e.key === "ArrowLeft") {
      e.preventDefault()
      focusIndex(selectedIndex - 1)
    } else if (e.key === "Home") {
      e.preventDefault()
      focusIndex(0)
    } else if (e.key === "End") {
      e.preventDefault()
      focusIndex(categories.length - 1)
    }
  }

  if (categories.length === 0) {
    return (
      <div
        className={cn(
          "rounded-xl border border-dashed border-black/[0.08] bg-white/60 px-4 py-3 text-xs text-[#86868b]",
          className,
        )}
      >
        Agents will appear here as the manifest arrives.
      </div>
    )
  }

  return (
    <div
      className={cn(
        "rounded-xl bg-white/60 p-2 ring-1 ring-black/[0.05]",
        className,
      )}
    >
      <div className="mb-1 flex items-center justify-between px-2">
        <div className="text-[11px] font-medium uppercase tracking-wide text-[#86868b]">
          Agents ({categories.length})
        </div>
        {selectedCategoryId && (
          <button
            type="button"
            onClick={() => onSelect(null)}
            className="text-[11px] text-[#86868b] transition-colors hover:text-[#1d1d1f]"
          >
            Clear
          </button>
        )}
      </div>
      <div
        ref={scrollerRef}
        role="tablist"
        aria-label="Evaluator agents"
        onKeyDown={handleKey}
        className="scrollbar-thin flex snap-x snap-mandatory gap-3 overflow-x-auto px-2 pb-2 pt-1"
      >
        {categories.map((c) => (
          <AgentCard
            key={c.category_id}
            ref={(el) => {
              if (el) cardRefs.current.set(c.category_id, el)
              else cardRefs.current.delete(c.category_id)
            }}
            category={c}
            selected={c.category_id === selectedCategoryId}
            onSelect={() => onSelect(c.category_id)}
          />
        ))}
      </div>
    </div>
  )
}

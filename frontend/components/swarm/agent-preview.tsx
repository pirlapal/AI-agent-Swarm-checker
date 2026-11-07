"use client"

import * as React from "react"
import { Sparkles } from "lucide-react"

import { cn } from "@/lib/utils"

import { CategorySwarmPanel, StatusPill } from "./category-swarm-panel"
import type { RunState } from "./run-state"

interface Props {
  state: RunState
  selectedCategoryId: string | null
  className?: string
}

type Section = {
  id: string
  label: string
}

const CATEGORY_SECTIONS: Section[] = [
  { id: "cat-overview", label: "Overview" },
  { id: "cat-thinking", label: "Thinking" },
  { id: "cat-tools", label: "Tools" },
  { id: "cat-findings", label: "Findings" },
  { id: "cat-summary", label: "Summary" },
]

/**
 * Right-hand panel. Default view = a terse Orchestrator overview with
 * refs-by-category breakdown + workflow metadata. Once an agent card in
 * the dock is clicked, swaps to the full CategorySwarmPanel for that
 * category with its own scroll + section-anchor tab bar.
 */
export function AgentPreview({
  state,
  selectedCategoryId,
  className,
}: Props) {
  const selected = React.useMemo(
    () =>
      selectedCategoryId
        ? state.categories.find((c) => c.category_id === selectedCategoryId)
        : null,
    [state.categories, selectedCategoryId],
  )

  const scrollTo = (id: string) => {
    const el = document.getElementById(id)
    if (!el) return
    el.scrollIntoView({ behavior: "smooth", block: "start" })
  }

  return (
    <aside
      role="tabpanel"
      aria-label="Agent preview"
      className={cn(
        "flex h-full flex-col overflow-hidden rounded-xl bg-white/60 ring-1 ring-black/[0.05]",
        className,
      )}
    >
      <header className="flex items-center justify-between gap-2 border-b border-black/[0.06] px-4 py-3">
        <div className="min-w-0">
          <div className="text-[11px] font-medium uppercase tracking-wide text-[#86868b]">
            {selected ? "Agent preview" : "Orchestrator overview"}
          </div>
          <div className="truncate text-sm font-semibold text-[#1d1d1f]">
            {selected ? selected.name : "Swarm overview"}
          </div>
        </div>
        {selected && <StatusPill status={selected.status} />}
      </header>

      {selected && (
        <nav className="scrollbar-thin flex gap-1 overflow-x-auto border-b border-black/[0.06] px-3 py-2">
          {CATEGORY_SECTIONS.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => scrollTo(s.id)}
              className="shrink-0 rounded-md px-2 py-1 text-[11px] font-medium text-[#86868b] transition-colors hover:bg-[#1d1d1f]/5 hover:text-[#1d1d1f]"
            >
              {s.label}
            </button>
          ))}
        </nav>
      )}

      <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {selected ? (
          <CategorySwarmPanel category={selected} bare />
        ) : (
          <OrchestratorOverview state={state} />
        )}
      </div>
    </aside>
  )
}

function OrchestratorOverview({ state }: { state: RunState }) {
  const totalRefs = state.categories.reduce((n, c) => n + c.refs.length, 0)
  const totalFindings = state.categories.reduce(
    (n, c) => n + c.findings.length,
    0,
  )
  const totalTools =
    state.orchestrator.toolCalls.length +
    state.categories.reduce((n, c) => n + c.toolCalls.length, 0)

  return (
    <div className="space-y-5">
      <section>
        <div className="mb-2 flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide text-[#86868b]">
          <Sparkles className="size-3 text-[#1d1d1f]" />
          Swarm status
        </div>
        <div className="grid grid-cols-3 gap-2">
          <Stat label="Agents" value={state.categories.length} />
          <Stat label="Refs" value={totalRefs} />
          <Stat label="Findings" value={totalFindings} />
        </div>
      </section>

      <section>
        <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-[#86868b]">
          Orchestrator
        </div>
        <div className="rounded-lg border border-black/[0.06] bg-white p-3 text-xs text-[#86868b]">
          <div className="flex items-center justify-between">
            <span>Status</span>
            <span className="font-medium text-[#1d1d1f]">
              {state.streamStatus}
            </span>
          </div>
          <div className="mt-1 flex items-center justify-between">
            <span>Tool calls</span>
            <span className="font-medium text-[#1d1d1f]">{totalTools}</span>
          </div>
          <div className="mt-1 flex items-center justify-between">
            <span>Internal steps</span>
            <span className="font-medium text-[#1d1d1f]">
              {state.orchestrator.internalSteps.length}
            </span>
          </div>
        </div>
      </section>

      {state.categories.length > 0 && (
        <section>
          <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-[#86868b]">
            Refs by category
          </div>
          <ul className="space-y-1.5">
            {state.categories.map((c) => (
              <li
                key={c.category_id}
                className="flex items-center justify-between rounded-md border border-black/[0.06] bg-white px-3 py-2"
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-medium text-[#1d1d1f]">
                    {c.name}
                  </div>
                  <div className="font-mono text-[10px] text-[#86868b]">
                    {c.category_id.slice(0, 8)}
                  </div>
                </div>
                <div className="flex items-center gap-2 text-[11px] text-[#86868b]">
                  <span>{c.refs.length} refs</span>
                  <StatusPill status={c.status} />
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {state.categories.length === 0 && (
        <div className="rounded-lg border border-dashed border-black/[0.08] bg-white/60 p-4 text-xs text-[#86868b]">
          Click an agent in the dock below to drill into its reasoning, tool
          calls, and findings.
        </div>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-black/[0.06] bg-white p-3">
      <div className="text-[10px] font-medium uppercase tracking-wide text-[#86868b]">
        {label}
      </div>
      <div className="mt-0.5 text-lg font-semibold text-[#1d1d1f]">{value}</div>
    </div>
  )
}

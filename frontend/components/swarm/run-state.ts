/**
 * Accumulates SwarmEvent frames into a per-category view model the
 * `CategorySwarmPanel` can render. One of these is kept in React state on
 * the run-live-view page and updated on every WS message.
 */

import type { SwarmEvent } from "@/lib/swarm-ws"

export interface ToolCallLog {
  id: string
  name: string
  args: Record<string, unknown>
  subagent?: string
  timestamp: number
}

export interface InternalStepLog {
  id: string
  tool: string
  description: string
  subagent?: string
  timestamp: number
}

export interface SubagentLifecycle {
  subagent: string
  startedAt: number
  endedAt?: number
}

export interface RuleFinding {
  rule_id: string
  status: "pass" | "fail" | "warning" | string
  detail?: string
  raw: Record<string, unknown>
  timestamp: number
}

export interface CategoryBucket {
  category_id: string
  name: string
  refs: string[]
  /** Streamed assistant tokens from the category's evaluator, concatenated. */
  tokens: string
  toolCalls: ToolCallLog[]
  internalSteps: InternalStepLog[]
  subagents: SubagentLifecycle[]
  findings: RuleFinding[]
  summary?: { status?: string; summary?: string; raw: Record<string, unknown> }
  status: "idle" | "running" | "complete"
}

export interface MapViewState {
  status: "idle" | "pending" | "ok" | "error"
  address?: string
  displayName?: string
  lat?: number
  lon?: number
  zoom?: number
  f4mapUrl?: string
  error?: string
  planId?: string
}

export interface RunState {
  /** "" before the manifest arrives. */
  workflowId: string
  caseId: string
  /** Human-readable plan identifier shared by the uploaded case files
   *  (e.g. `138-24_1`). Empty until the first event that carries it. */
  planId: string
  caseFiles: { filename: string }[]
  categories: CategoryBucket[]
  /** Anything without a resolvable category ends up here. */
  orchestrator: Omit<CategoryBucket, "category_id" | "name" | "refs">
  caseSummary?: { raw: Record<string, unknown>; text?: string }
  /** Populated when the orchestrator's `show_property_map` tool call
   *  finishes. `idle` = never dispatched; `pending` = waiting for the
   *  first `map_view` event. */
  mapView: MapViewState
  streamStatus: "connecting" | "live" | "done" | "error"
  errorMessage?: string
}

export const emptyRunState = (): RunState => ({
  workflowId: "",
  caseId: "",
  planId: "",
  caseFiles: [],
  categories: [],
  orchestrator: {
    tokens: "",
    toolCalls: [],
    internalSteps: [],
    subagents: [],
    findings: [],
    status: "running",
  },
  mapView: { status: "idle" },
  streamStatus: "connecting",
})

const ensureCategoryById = (
  state: RunState,
  category_id: string | undefined,
): RunState => {
  if (!category_id) return state
  if (state.categories.some((c) => c.category_id === category_id)) return state
  return {
    ...state,
    categories: [
      ...state.categories,
      {
        category_id,
        name: category_id,
        refs: [],
        tokens: "",
        toolCalls: [],
        internalSteps: [],
        subagents: [],
        findings: [],
        status: "running",
      },
    ],
  }
}

/**
 * Turn a subagent label from streaming.py into a category_id. The backend
 * names evaluators `evaluator_{category_id}`; the orchestrator's own label
 * comes through as empty or `orchestrator`.
 */
export const subagentToCategoryId = (
  subagent: string | undefined,
): string | undefined => {
  if (!subagent) return undefined
  if (subagent.startsWith("evaluator_")) return subagent.slice("evaluator_".length)
  return undefined
}

export function applySwarmEvent(state: RunState, event: SwarmEvent): RunState {
  switch (event.type) {
    case "metadata": {
      const planId =
        typeof (event as { plan_id?: unknown }).plan_id === "string"
          ? ((event as { plan_id: string }).plan_id)
          : ""
      if (!planId || planId === state.planId) return state
      return { ...state, planId }
    }

    case "manifest": {
      const refsByCat =
        event.reference_files_by_category || event.refs_by_category || {}
      const categoryEntries = Object.entries(refsByCat).map(
        ([category_id, files]) => ({
          category_id,
          name: category_id,
          refs: (files || []).map((f) => f.filename),
          tokens: "",
          toolCalls: [] as ToolCallLog[],
          internalSteps: [] as InternalStepLog[],
          subagents: [] as SubagentLifecycle[],
          findings: [] as RuleFinding[],
          status: "idle" as const,
        }),
      )
      return {
        ...state,
        workflowId: event.workflow_id,
        caseId: event.case_id,
        planId: event.plan_id || state.planId,
        caseFiles: event.case_files || [],
        categories: categoryEntries,
        streamStatus: "live",
      }
    }

    case "token": {
      const catId = subagentToCategoryId(event.subagent)
      if (!catId) {
        return {
          ...state,
          orchestrator: {
            ...state.orchestrator,
            tokens: state.orchestrator.tokens + event.content,
          },
        }
      }
      const next = ensureCategoryById(state, catId)
      return {
        ...next,
        categories: next.categories.map((cat) =>
          cat.category_id === catId
            ? {
                ...cat,
                tokens: cat.tokens + event.content,
                status: "running",
              }
            : cat,
        ),
      }
    }

    case "tool_call": {
      const entry: ToolCallLog = {
        id: event.id || `${event.name}-${Date.now()}`,
        name: event.name,
        args: (event.args as Record<string, unknown>) || {},
        subagent: event.subagent,
        timestamp: Date.now(),
      }
      const catId = subagentToCategoryId(event.subagent)
      // TODO(map): re-enable when the F4Map live-view tool is wired
      // back in. Previously, seeing the orchestrator fire
      // `show_property_map` would flip mapView to "pending" here so
      // the UI could show a "Locating property..." placeholder before
      // the `map_view` event arrived. Disabled alongside the backend
      // registration.
      // const mapView: MapViewState =
      //   event.name === "show_property_map" && state.mapView.status === "idle"
      //     ? {
      //         status: "pending",
      //         address:
      //           typeof (entry.args as { address?: unknown }).address ===
      //           "string"
      //             ? ((entry.args as { address: string }).address)
      //             : undefined,
      //         planId: state.planId || undefined,
      //       }
      //     : state.mapView
      const mapView = state.mapView
      if (!catId) {
        return {
          ...state,
          mapView,
          orchestrator: {
            ...state.orchestrator,
            toolCalls: [...state.orchestrator.toolCalls, entry],
          },
        }
      }
      const next = ensureCategoryById(state, catId)
      return {
        ...next,
        mapView,
        categories: next.categories.map((cat) =>
          cat.category_id === catId
            ? { ...cat, toolCalls: [...cat.toolCalls, entry] }
            : cat,
        ),
      }
    }

    case "internal_step": {
      const entry: InternalStepLog = {
        id: `${event.tool}-${Date.now()}`,
        tool: event.tool,
        description: event.description,
        subagent: event.subagent,
        timestamp: Date.now(),
      }
      const catId = subagentToCategoryId(event.subagent)
      if (!catId) {
        return {
          ...state,
          orchestrator: {
            ...state.orchestrator,
            internalSteps: [...state.orchestrator.internalSteps, entry],
          },
        }
      }
      const next = ensureCategoryById(state, catId)
      return {
        ...next,
        categories: next.categories.map((cat) =>
          cat.category_id === catId
            ? { ...cat, internalSteps: [...cat.internalSteps, entry] }
            : cat,
        ),
      }
    }

    case "subagent_start": {
      const catId = subagentToCategoryId(event.subagent)
      const entry: SubagentLifecycle = {
        subagent: event.subagent,
        startedAt: Date.now(),
      }
      if (!catId) {
        return {
          ...state,
          orchestrator: {
            ...state.orchestrator,
            subagents: [...state.orchestrator.subagents, entry],
          },
        }
      }
      const next = ensureCategoryById(state, catId)
      return {
        ...next,
        categories: next.categories.map((cat) =>
          cat.category_id === catId
            ? {
                ...cat,
                subagents: [...cat.subagents, entry],
                status: "running",
              }
            : cat,
        ),
      }
    }

    case "subagent_end": {
      const catId = subagentToCategoryId(event.subagent)
      const markEnded = (list: SubagentLifecycle[]) => {
        const idx = [...list]
          .reverse()
          .findIndex((s) => s.subagent === event.subagent && !s.endedAt)
        if (idx === -1) return list
        const real = list.length - 1 - idx
        return list.map((s, i) => (i === real ? { ...s, endedAt: Date.now() } : s))
      }
      if (!catId) {
        return {
          ...state,
          orchestrator: {
            ...state.orchestrator,
            subagents: markEnded(state.orchestrator.subagents),
          },
        }
      }
      return {
        ...state,
        categories: state.categories.map((cat) =>
          cat.category_id === catId
            ? { ...cat, subagents: markEnded(cat.subagents) }
            : cat,
        ),
      }
    }

    case "catalog": {
      const docs =
        (event.documents as unknown[] | undefined) ||
        (event.entries as unknown[] | undefined) ||
        []
      const planId = event.plan_id || state.planId
      return {
        ...state,
        planId,
        orchestrator: {
          ...state.orchestrator,
          internalSteps: [
            ...state.orchestrator.internalSteps,
            {
              id: `catalog-${Date.now()}`,
              tool: "catalog_documents",
              description: `Cataloged ${docs.length} documents`,
              timestamp: Date.now(),
            },
          ],
        },
      }
    }

    case "map_view": {
      // TODO(map): re-enable when the F4Map live-view tool is wired
      // back in on the backend. The streaming layer's whitelist no
      // longer forwards `show_property_map` tool messages, so a
      // `map_view` event should never arrive -- but if one does
      // (e.g. from an old run replayed against a newer UI), treat it
      // as a no-op instead of flipping the reducer's mapView state.
      //
      // Previous implementation:
      // const addr = typeof event.address === "string" ? event.address : ""
      // const planId = event.plan_id || state.planId
      // const zoom = typeof event.zoom === "number" ? event.zoom : undefined
      // if (event.status === "error") {
      //   return {
      //     ...state,
      //     planId,
      //     mapView: {
      //       status: "error",
      //       address: addr || undefined,
      //       zoom,
      //       error: event.error || "Geocoding failed.",
      //       planId: planId || undefined,
      //     },
      //   }
      // }
      // const lat = event.resolved?.lat
      // const lon = event.resolved?.lon
      // const f4 = typeof event.f4map_url === "string" ? event.f4map_url : undefined
      // if (typeof lat !== "number" || typeof lon !== "number" || !f4) {
      //   return {
      //     ...state,
      //     planId,
      //     mapView: {
      //       status: "error",
      //       address: addr || undefined,
      //       zoom,
      //       error: "Malformed map_view payload: missing coordinates or URL.",
      //       planId: planId || undefined,
      //     },
      //   }
      // }
      // return {
      //   ...state,
      //   planId,
      //   mapView: {
      //     status: "ok",
      //     address: addr || undefined,
      //     displayName: event.resolved?.display_name,
      //     lat,
      //     lon,
      //     zoom,
      //     f4mapUrl: f4,
      //     planId: planId || undefined,
      //   },
      // }
      //
      // Still capture plan_id if the stray event happens to carry one.
      const planId = event.plan_id || state.planId
      return planId === state.planId ? state : { ...state, planId }
    }

    case "category_result": {
      // Envelope: { type: "category_result", finding: { category_id,
      // rule_id, status: "PASS"|"FAIL"|"NEEDS_REVIEW", reason, ... } }
      // (see agent/tools.py:121-135). Backwards-compat: some older
      // builds flattened these onto the root.
      const rawEvent = event as unknown as {
        finding?: Record<string, unknown>
        category_id?: string
        rule_id?: string
        status?: string
        reason?: string
        detail?: string
      }
      const finding = rawEvent.finding || {
        category_id: rawEvent.category_id,
        rule_id: rawEvent.rule_id,
        status: rawEvent.status,
        reason: rawEvent.reason || rawEvent.detail,
      }
      const catId =
        typeof finding.category_id === "string" ? finding.category_id : ""
      if (!catId) return state
      const rawStatus = String(finding.status || "").toUpperCase()
      const normalized: RuleFinding["status"] =
        rawStatus === "PASS"
          ? "pass"
          : rawStatus === "FAIL"
            ? "fail"
            : rawStatus === "NEEDS_REVIEW" || rawStatus === "WARNING"
              ? "warning"
              : rawStatus.toLowerCase() || "warning"
      const detail =
        typeof finding.reason === "string"
          ? finding.reason
          : typeof (finding as { detail?: unknown }).detail === "string"
            ? ((finding as { detail: string }).detail)
            : undefined
      const next = ensureCategoryById(state, catId)
      const fndEntry: RuleFinding = {
        rule_id:
          typeof finding.rule_id === "string" ? finding.rule_id : "",
        status: normalized,
        detail,
        raw: finding as Record<string, unknown>,
        timestamp: Date.now(),
      }
      return {
        ...next,
        categories: next.categories.map((cat) =>
          cat.category_id === catId
            ? { ...cat, findings: [...cat.findings, fndEntry] }
            : cat,
        ),
      }
    }

    case "category_summary": {
      // Envelope: { type: "category_summary", summary: { category_id,
      // overall_status, summary, plan_id, ... } } (see agent/tools.py).
      const rawEvent = event as unknown as {
        summary?: Record<string, unknown>
        category_id?: string
        status?: string
      }
      const summaryObj = rawEvent.summary || {
        category_id: rawEvent.category_id,
        overall_status: rawEvent.status,
      }
      const catId =
        typeof summaryObj.category_id === "string"
          ? summaryObj.category_id
          : rawEvent.category_id || ""
      if (!catId) return state
      const planId =
        typeof summaryObj.plan_id === "string" && summaryObj.plan_id
          ? (summaryObj.plan_id as string)
          : state.planId
      const next = ensureCategoryById({ ...state, planId }, catId)
      const statusStr =
        typeof summaryObj.overall_status === "string"
          ? summaryObj.overall_status
          : typeof (summaryObj as { status?: unknown }).status === "string"
            ? ((summaryObj as { status: string }).status)
            : undefined
      const summaryText =
        typeof summaryObj.summary === "string" ? summaryObj.summary : undefined
      return {
        ...next,
        categories: next.categories.map((cat) =>
          cat.category_id === catId
            ? {
                ...cat,
                summary: {
                  status: statusStr,
                  summary: summaryText,
                  raw: summaryObj as Record<string, unknown>,
                },
                status: "complete",
              }
            : cat,
        ),
      }
    }

    case "case_summary": {
      // Envelope: { type: "case_summary", summary: { overall_status,
      // summary, categories, ... } } (see agent/tools.py:268-284).
      // Older builds used { report: ... }; keep that path alive.
      const rawEvent = event as unknown as {
        summary?: Record<string, unknown>
        report?: unknown
      }
      const summaryObj = rawEvent.summary
      const report = rawEvent.report
      let text: string | undefined
      if (summaryObj && typeof summaryObj.summary === "string") {
        text = summaryObj.summary
      } else if (typeof report === "string") {
        text = report
      } else if (
        report &&
        typeof report === "object" &&
        "markdown" in report &&
        typeof (report as { markdown?: unknown }).markdown === "string"
      ) {
        text = (report as { markdown: string }).markdown
      }
      const raw: Record<string, unknown> =
        (summaryObj as Record<string, unknown> | undefined) ||
        (typeof report === "object" && report !== null
          ? (report as Record<string, unknown>)
          : (event as unknown as Record<string, unknown>))
      const planId =
        summaryObj && typeof summaryObj.plan_id === "string" && summaryObj.plan_id
          ? (summaryObj.plan_id as string)
          : state.planId
      return {
        ...state,
        planId,
        caseSummary: { raw, text },
      }
    }

    case "done":
      return {
        ...state,
        streamStatus: "done",
        orchestrator: { ...state.orchestrator, status: "complete" },
        categories: state.categories.map((cat) => ({ ...cat, status: "complete" })),
      }

    case "error":
      return {
        ...state,
        streamStatus: "error",
        errorMessage: event.message,
      }

    default:
      return state
  }
}

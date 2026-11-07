"use client"

import * as React from "react"
import { AlertTriangle, CheckCircle2, Loader2, Radio } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { openSwarmStream, type SwarmStreamHandle } from "@/lib/swarm-ws"

import { AgentDock } from "./agent-dock"
import { AgentPreview } from "./agent-preview"
import { ChatStream } from "./chat-stream"
// TODO(map): re-enable when the F4Map live-view tool is wired back in.
// import { MapViewPanel } from "./map-view-panel"
import {
  applySwarmEvent,
  emptyRunState,
  type RunState,
} from "./run-state"

interface Props {
  workflowId: string
  workflowName?: string
  caseId: string
  userId?: string
  /** Forwarded to the local agent's `start` frame. Ignored in cloud mode. */
  userPrompt?: string
  /** Called when user clicks "new run"/"back". */
  onReset?: () => void
}

function StreamBadge({ status }: { status: RunState["streamStatus"] }) {
  if (status === "connecting") {
    return (
      <Badge
        variant="outline"
        className="border-black/[0.08] bg-white text-xs text-[#86868b]"
      >
        <Loader2 className="mr-1 size-3 animate-spin" />
        Connecting
      </Badge>
    )
  }
  if (status === "live") {
    return (
      <Badge
        variant="outline"
        className="border-[#34c759]/20 bg-[#34c759]/10 text-xs text-[#34c759]"
      >
        <Radio className="mr-1 size-3" />
        Live
      </Badge>
    )
  }
  if (status === "done") {
    return (
      <Badge
        variant="outline"
        className="border-black/[0.08] bg-white text-xs text-[#1d1d1f]"
      >
        <CheckCircle2 className="mr-1 size-3" />
        Done
      </Badge>
    )
  }
  return (
    <Badge
      variant="outline"
      className="border-[#ff3b30]/20 bg-[#ff3b30]/10 text-xs text-[#ff3b30]"
    >
      <AlertTriangle className="mr-1 size-3" />
      Error
    </Badge>
  )
}

export function RunLiveView({
  workflowId,
  workflowName,
  caseId,
  userId,
  userPrompt,
  onReset,
}: Props) {
  const [state, setState] = React.useState<RunState>(() => emptyRunState())
  const handleRef = React.useRef<SwarmStreamHandle | null>(null)

  // `null` = Orchestrator overview in the right panel. Once the user
  // clicks an agent card, we pin to that choice and stop auto-following.
  const [selectedCategoryId, setSelectedCategoryId] = React.useState<
    string | null
  >(null)
  const [manualSelect, setManualSelect] = React.useState(false)

  React.useEffect(() => {
    let cancelled = false
    setState(emptyRunState())
    setSelectedCategoryId(null)
    setManualSelect(false)

    openSwarmStream({
      workflowId,
      caseId,
      userId,
      userPrompt,
      onEvent: (event) => {
        if (cancelled) return
        setState((prev) => applySwarmEvent(prev, event))
      },
      onOpen: () => {
        if (cancelled) return
        setState((prev) => ({ ...prev, streamStatus: "live" }))
      },
    })
      .then((handle) => {
        if (cancelled) {
          handle.close()
          return
        }
        handleRef.current = handle
      })
      .catch((err) => {
        if (cancelled) return
        console.error("[RunLiveView] failed to open stream", err)
        setState((prev) => ({
          ...prev,
          streamStatus: "error",
          errorMessage: err?.message || "Failed to open stream.",
        }))
      })

    return () => {
      cancelled = true
      handleRef.current?.close()
      handleRef.current = null
    }
  }, [workflowId, caseId, userId, userPrompt])

  // Auto-follow: while the user hasn't picked an agent, keep the
  // preview+inline-chat focused on whichever category is currently
  // streaming. Falls through to Orchestrator when nothing is streaming.
  React.useEffect(() => {
    if (manualSelect) return
    const streaming = state.categories.find((c) => c.status === "running")
    if (streaming) {
      setSelectedCategoryId(streaming.category_id)
      return
    }
    if (state.categories.length > 0 && selectedCategoryId === null) {
      // Keep null so the overview shows until we have something live.
    }
  }, [state.categories, manualSelect, selectedCategoryId])

  const handleSelect = (id: string | null) => {
    setManualSelect(true)
    setSelectedCategoryId(id)
  }

  return (
    <div className="flex h-full flex-col gap-4">
      <Card className="glass-card shadow-depth-2">
        <CardContent className="flex flex-wrap items-center justify-between gap-4 p-5">
          <div>
            <div className="text-xs text-[#86868b]">
              Case · {caseId.slice(0, 8)}
            </div>
            <div className="mt-0.5 text-2xl font-semibold text-[#1d1d1f]">
              {workflowName || "Workflow"}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <StreamBadge status={state.streamStatus} />
            {state.planId && (
              <Badge
                variant="outline"
                className="border-black/[0.08] bg-white text-xs text-[#1d1d1f]"
              >
                Plan {state.planId}
              </Badge>
            )}
            {onReset && (
              <button
                type="button"
                onClick={onReset}
                className="text-sm text-[#86868b] transition-colors hover:text-[#1d1d1f]"
              >
                New run →
              </button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* TODO(map): re-enable when the show_property_map tool is
          wired back in on the backend.
      {state.mapView.status !== "idle" && (
        <MapViewPanel mapView={state.mapView} planId={state.planId} />
      )}
      */}

      <div
        className="grid min-h-0 flex-1 gap-4"
        style={{
          gridTemplateColumns: "minmax(0, 1fr) minmax(280px, 360px)",
          gridTemplateRows: "minmax(0, 1fr) auto",
        }}
      >
        <div className="col-start-1 row-start-1 min-h-0 overflow-hidden">
          <ChatStream
            state={state}
            activeCategoryId={selectedCategoryId}
            className="h-full"
          />
        </div>
        <div className="col-start-2 row-start-1 min-h-0 overflow-hidden">
          <AgentPreview
            state={state}
            selectedCategoryId={selectedCategoryId}
            className="h-full"
          />
        </div>
        <AgentDock
          categories={state.categories}
          selectedCategoryId={selectedCategoryId}
          onSelect={handleSelect}
          className="col-span-2 row-start-2"
        />
      </div>
    </div>
  )
}

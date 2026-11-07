/**
 * Swarm AgentCore WebSocket client.
 *
 * Two modes, selected at build time:
 *
 * 1. **Local** -- when `NEXT_PUBLIC_LOCAL_AGENT_WS_URL` is set (e.g.
 *    `ws://localhost:8080/ws`), we skip presigning entirely and open the
 *    socket directly to the docker container. The local agent is lazy:
 *    it waits for a `{"type":"start", workflow_id, case_id, user_prompt,
 *    throttle?}` frame from the client before doing anything (see
 *    `agent/app.py:77-87`). We send that frame on `open`.
 *
 * 2. **Cloud** -- default. POST `/caseWsPresign` (on
 *    `NEXT_PUBLIC_WS_PRESIGN_API_BASE_URL`) to get a SigV4 pre-signed
 *    `wss://` URL, then open a single WebSocket to that URL. The
 *    AgentCore runtime starts streaming as soon as the socket opens --
 *    no client-sent start frame is needed there.
 *
 * Event envelopes follow `swarm-agentcore-agent/agent/streaming.py` and
 * `agent/tools.py`. We do NOT auto-reconnect: pre-signed URLs are
 * single-use, and a local reconnect would duplicate runs. On unexpected
 * close we emit a terminal `{ type: "error" }` so the UI can surface it.
 */

import { getCaseWsPresignedUrl } from "@/lib/api"

export type SwarmAgentLabel = string

/**
 * `category_result.finding`, `category_summary.summary`, and
 * `case_summary.summary` carry the interesting data for those events.
 * We type them loosely here and let the reducer shape them down.
 */
export interface RuleFindingPayload {
  category_id?: string
  rule_id?: string
  status?: "PASS" | "FAIL" | "NEEDS_REVIEW" | string
  reason?: string
  [extra: string]: unknown
}

export interface CategorySummaryPayload {
  category_id?: string
  overall_status?: string
  summary?: string
  [extra: string]: unknown
}

export interface CaseSummaryPayload {
  overall_status?: string
  summary?: string
  categories?: Array<Record<string, unknown>>
  [extra: string]: unknown
}

export type SwarmEvent =
  | { type: "metadata"; thread_id?: string; plan_id?: string; [extra: string]: unknown }
  | {
      type: "manifest"
      workflow_id: string
      case_id: string
      plan_id?: string
      case_files?: { filename: string; s3_key?: string }[]
      reference_files_by_category?: Record<
        string,
        { filename: string; s3_key?: string }[]
      >
      /** `test_workflow.py` reads this alias; we accept both. */
      refs_by_category?: Record<
        string,
        { filename: string; s3_key?: string }[]
      >
    }
  | { type: "token"; content: string; subagent?: SwarmAgentLabel }
  | {
      type: "tool_call"
      id?: string
      name: string
      args: Record<string, unknown>
      subagent?: SwarmAgentLabel
    }
  | {
      type: "internal_step"
      node: string
      tool: string
      description: string
      args: Record<string, unknown>
      subagent?: SwarmAgentLabel
    }
  | { type: "subagent_start"; subagent: string; namespace: string }
  | { type: "subagent_end"; subagent: string }
  | {
      type: "catalog"
      documents?: Array<Record<string, unknown>>
      entries?: Array<Record<string, unknown>>
      plan_id?: string
      subagent?: SwarmAgentLabel
      [extra: string]: unknown
    }
  | {
      type: "map_view"
      workflow_id?: string
      case_id?: string
      plan_id?: string
      address?: string
      zoom?: number
      resolved?: { lat: number; lon: number; display_name?: string }
      f4map_url?: string
      status?: "ok" | "error"
      error?: string
      subagent?: SwarmAgentLabel
    }
  | {
      type: "category_result"
      finding?: RuleFindingPayload
      subagent?: SwarmAgentLabel
    }
  | {
      type: "category_summary"
      summary?: CategorySummaryPayload
      subagent?: SwarmAgentLabel
    }
  | {
      type: "case_summary"
      summary?: CaseSummaryPayload
      subagent?: SwarmAgentLabel
    }
  | { type: "done" }
  | { type: "error"; message: string }
  // Keep-alives / ack messages we ignore.
  | { type: "pong" }
  | { type: "stopped"; reason?: string }

export interface SwarmStreamHandle {
  close: () => void
  socket: WebSocket
  sessionId: string
}

export interface OpenSwarmStreamArgs {
  workflowId: string
  caseId: string
  userId?: string
  /** Forwarded to the local agent's `start` frame; ignored in cloud mode. */
  userPrompt?: string
  onEvent: (event: SwarmEvent) => void
  onOpen?: () => void
  onClose?: (ev: CloseEvent) => void
}

const LOCAL_WS_URL = (process.env.NEXT_PUBLIC_LOCAL_AGENT_WS_URL || "").trim()

function attachHandlers(
  socket: WebSocket,
  onEvent: OpenSwarmStreamArgs["onEvent"],
  onOpen: OpenSwarmStreamArgs["onOpen"],
  onClose: OpenSwarmStreamArgs["onClose"],
  closedByUserRef: { current: boolean },
  afterOpen?: () => void,
) {
  socket.addEventListener("open", () => {
    onOpen?.()
    afterOpen?.()
  })

  socket.addEventListener("message", (ev) => {
    const raw = typeof ev.data === "string" ? ev.data : null
    if (!raw) return
    let parsed: SwarmEvent | null = null
    try {
      parsed = JSON.parse(raw) as SwarmEvent
    } catch (err) {
      console.error("[swarm-ws] malformed frame", err, raw)
      onEvent({ type: "error", message: "Malformed frame from runtime." })
      return
    }
    if (!parsed || typeof parsed !== "object" || !("type" in parsed)) {
      return
    }
    // Silently drop keep-alives; they're noise for the reducer.
    if (parsed.type === "pong" || parsed.type === "stopped") return
    onEvent(parsed)
  })

  socket.addEventListener("error", () => {
    onEvent({ type: "error", message: "WebSocket error." })
  })

  socket.addEventListener("close", (ev) => {
    if (!closedByUserRef.current && ev.code !== 1000) {
      onEvent({
        type: "error",
        message: `Runtime connection closed (code ${ev.code}).`,
      })
    }
    onClose?.(ev)
  })
}

function makeHandle(
  socket: WebSocket,
  sessionId: string,
  closedByUserRef: { current: boolean },
): SwarmStreamHandle {
  return {
    close: () => {
      closedByUserRef.current = true
      if (
        socket.readyState === WebSocket.OPEN ||
        socket.readyState === WebSocket.CONNECTING
      ) {
        socket.close(1000, "client closed")
      }
    },
    socket,
    sessionId,
  }
}

export async function openSwarmStream({
  workflowId,
  caseId,
  userId,
  userPrompt,
  onEvent,
  onOpen,
  onClose,
}: OpenSwarmStreamArgs): Promise<SwarmStreamHandle> {
  const closedByUserRef = { current: false }

  // ── Local dev mode ────────────────────────────────────────
  if (LOCAL_WS_URL) {
    const socket = new WebSocket(LOCAL_WS_URL)
    attachHandlers(socket, onEvent, onOpen, onClose, closedByUserRef, () => {
      // Local agent is lazy: kick it with a `start` frame mirroring
      // test_workflow.py's shape.
      const startFrame = {
        type: "start",
        workflow_id: workflowId,
        case_id: caseId,
        user_prompt: userPrompt || "",
        throttle: {
          pdf_delay_ms: 1500,
          max_retries: 10,
          backoff_mode: "adaptive",
        },
      }
      try {
        socket.send(JSON.stringify(startFrame))
      } catch (err) {
        console.error("[swarm-ws] failed to send start frame", err)
        onEvent({
          type: "error",
          message: "Failed to send start frame to local agent.",
        })
      }
    })
    return makeHandle(socket, "local", closedByUserRef)
  }

  // ── Cloud (SigV4 presigned) ────────────────────────────────
  const presign = await getCaseWsPresignedUrl({
    workflow_id: workflowId,
    case_id: caseId,
    user_id: userId,
  })

  const socket = new WebSocket(presign.url)
  attachHandlers(socket, onEvent, onOpen, onClose, closedByUserRef)
  return makeHandle(socket, presign.session_id, closedByUserRef)
}

/**
 * Presentation helpers shared by OrchestratorBlock and CategoryBlock.
 *
 * Kept intentionally small and dependency-free so both server and client
 * components can import them without pulling in React.
 */

import type { DynamicToolUIPart } from "ai"

import type { InternalStepLog, ToolCallLog } from "./run-state"

export interface DedupedStep extends InternalStepLog {
  count: number
}

/**
 * Collapse consecutive internal-step events with the same tool+description
 * into a single entry with a count. The AgentCore orchestrator emits a
 * fresh `task` step every time it delegates to an evaluator, which
 * produces runs like `task Delegating to sub-agent: evaluator_abc` fifteen
 * times in a row. This turns that wall into `Delegating to sub-agent:
 * evaluator_abc ×15`.
 */
export function dedupeSteps(steps: InternalStepLog[]): DedupedStep[] {
  const out: DedupedStep[] = []
  for (const step of steps) {
    const prev = out[out.length - 1]
    if (
      prev &&
      prev.tool === step.tool &&
      prev.description === step.description
    ) {
      prev.count += 1
      prev.timestamp = step.timestamp
      continue
    }
    out.push({ ...step, count: 1 })
  }
  return out
}

/**
 * Shape a `ToolCallLog` from run-state into the AI SDK's
 * `DynamicToolUIPart` so it can be passed straight into
 * `<ToolHeader type="dynamic-tool" toolName state />` without a custom
 * component. The SDK drives the collapsible, status badge, and JSON
 * formatting from this shape.
 */
export function toToolUIPart(
  tc: ToolCallLog,
  isDone: boolean,
): DynamicToolUIPart {
  return {
    type: "dynamic-tool",
    toolName: tc.name,
    toolCallId: tc.id,
    state: isDone ? "output-available" : "input-available",
    input: tc.args,
  } as DynamicToolUIPart
}

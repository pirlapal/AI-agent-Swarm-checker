"use client"

import * as React from "react"
import { Hammer, Sparkles, Users } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import {
  ChainOfThought,
  ChainOfThoughtContent,
  ChainOfThoughtHeader,
  ChainOfThoughtStep,
} from "@/components/ai-elements/chain-of-thought"
import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message"
import {
  Tool,
  ToolContent,
  ToolHeader,
  ToolInput,
} from "@/components/ai-elements/tool"

import type { RunState } from "./run-state"
import { dedupeSteps, toToolUIPart } from "./step-utils"

interface Props {
  orchestrator: RunState["orchestrator"]
  streamStatus: RunState["streamStatus"]
}

/**
 * Renders the root orchestrator's reasoning, tool calls, and streaming
 * markdown output. Replaces the inline <ul> + pre-wrap text block that
 * produced the `task Delegating to sub-agent... task Delegating...` wall.
 */
export function OrchestratorBlock({ orchestrator, streamStatus }: Props) {
  const steps = React.useMemo(
    () => dedupeSteps(orchestrator.internalSteps),
    [orchestrator.internalSteps],
  )
  const isLive = streamStatus === "live"
  const isDone = streamStatus === "done"

  const hasContent =
    steps.length > 0 ||
    orchestrator.toolCalls.length > 0 ||
    orchestrator.tokens.length > 0

  if (!hasContent) return null

  return (
    <Message from="assistant" className="max-w-full">
      <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide text-[#86868b]">
        <span className="inline-flex size-5 items-center justify-center rounded-full bg-[#1d1d1f]/5">
          <Sparkles className="size-3 text-[#1d1d1f]" />
        </span>
        Orchestrator
        {orchestrator.status === "complete" && (
          <Badge
            variant="outline"
            className="border-black/[0.08] bg-white text-[10px] text-[#86868b]"
          >
            idle
          </Badge>
        )}
      </div>

      <MessageContent className="gap-4">
        {steps.length > 0 && (
          <ChainOfThought defaultOpen>
            <ChainOfThoughtHeader>
              Orchestrator reasoning ({steps.length}
              {steps.length === 1 ? " step" : " steps"})
            </ChainOfThoughtHeader>
            <ChainOfThoughtContent>
              {steps.map((step) => {
                const Icon = step.tool === "task" ? Users : Hammer
                return (
                  <ChainOfThoughtStep
                    key={step.id}
                    icon={Icon}
                    label={
                      <span className="flex items-baseline gap-2">
                        <span>{step.description}</span>
                        {step.count > 1 && (
                          <span className="rounded-full bg-[#1d1d1f]/5 px-1.5 py-0.5 font-mono text-[10px] text-[#86868b]">
                            ×{step.count}
                          </span>
                        )}
                      </span>
                    }
                    description={`internal · ${step.tool}`}
                    status="complete"
                  />
                )
              })}
            </ChainOfThoughtContent>
          </ChainOfThought>
        )}

        {orchestrator.toolCalls.length > 0 && (
          <div className="space-y-2">
            <div className="text-[11px] font-medium uppercase tracking-wide text-[#86868b]">
              Tool calls ({orchestrator.toolCalls.length})
            </div>
            {orchestrator.toolCalls.map((tc) => {
              const part = toToolUIPart(tc, isDone)
              return (
                <Tool key={tc.id} defaultOpen={false}>
                  <ToolHeader
                    type="dynamic-tool"
                    toolName={tc.name}
                    state={part.state}
                  />
                  <ToolContent>
                    <ToolInput input={part.input} />
                  </ToolContent>
                </Tool>
              )
            })}
          </div>
        )}

        {orchestrator.tokens && (
          <div className="prose prose-neutral max-w-none text-sm leading-relaxed text-[#1d1d1f]">
            <MessageResponse parseIncompleteMarkdown={isLive}>
              {orchestrator.tokens}
            </MessageResponse>
            {isLive && <span className="caret text-[#1d1d1f]" aria-hidden />}
          </div>
        )}
      </MessageContent>
    </Message>
  )
}

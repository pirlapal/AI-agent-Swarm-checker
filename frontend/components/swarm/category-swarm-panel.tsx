"use client"

import * as React from "react"
import {
  CheckCircle2,
  CircleDot,
  Hammer,
  Loader2,
  Users,
  XCircle,
} from "lucide-react"

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
  Reasoning,
  ReasoningContent,
  ReasoningTrigger,
} from "@/components/ai-elements/reasoning"
import {
  Task,
  TaskContent,
  TaskItem,
  TaskTrigger,
} from "@/components/ai-elements/task"
import {
  Tool,
  ToolContent,
  ToolHeader,
  ToolInput,
} from "@/components/ai-elements/tool"

import type { CategoryBucket } from "./run-state"
import { dedupeSteps, toToolUIPart } from "./step-utils"

/**
 * Status pill shared by the preview panel, chat stream summary cards, and
 * the agent dock cards so all three places show identical wording for
 * idle/streaming/complete.
 */
export function StatusPill({ status }: { status: CategoryBucket["status"] }) {
  if (status === "complete") {
    return (
      <Badge
        variant="outline"
        className="border-[#34c759]/20 bg-[#34c759]/10 text-xs text-[#34c759]"
      >
        <CheckCircle2 className="mr-1 size-3" />
        Complete
      </Badge>
    )
  }
  if (status === "running") {
    return (
      <Badge
        variant="outline"
        className="border-black/[0.08] bg-white text-xs text-[#1d1d1f]"
      >
        <Loader2 className="mr-1 size-3 animate-spin" />
        Streaming
      </Badge>
    )
  }
  return (
    <Badge
      variant="outline"
      className="border-black/[0.08] bg-white text-xs text-[#86868b]"
    >
      <CircleDot className="mr-1 size-3" />
      Idle
    </Badge>
  )
}

function FindingIcon({ status }: { status: string }) {
  if (status === "pass")
    return <CheckCircle2 className="size-3.5 text-[#34c759]" />
  if (status === "fail") return <XCircle className="size-3.5 text-[#ff3b30]" />
  return <CircleDot className="size-3.5 text-[#ff9f0a]" />
}

interface Props {
  category: CategoryBucket
  /**
   * When true, hides the outer Message+header chrome so the caller
   * (AgentPreview) can provide its own chrome. Defaults to false so
   * direct usage in the chat still looks like a chat message.
   */
  bare?: boolean
}

/**
 * Full rich view of a single category (evaluator + its subagents). Used
 * by the right-hand AgentPreview and also as a drop-in message inside
 * the chat stream. Each sub-section is rendered through the AI Elements
 * SDK so streaming markdown, collapsible tool calls, and the reasoning
 * shimmer all come along for free.
 */
export function CategorySwarmPanel({ category, bare = false }: Props) {
  const refCount = category.refs.length
  const findingCount = category.findings.length
  const steps = React.useMemo(
    () => dedupeSteps(category.internalSteps),
    [category.internalSteps],
  )
  const isDone = category.status === "complete"
  const isRunning = category.status === "running"

  const body = (
    <>
      <header id="cat-overview" className="scroll-mt-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="rounded bg-[#1d1d1f]/5 px-2 py-1 font-mono text-[11px] font-medium text-[#86868b]">
              {category.category_id.slice(0, 6)}
            </span>
            <h3 className="text-xl font-semibold leading-tight text-[#1d1d1f]">
              {category.name}
            </h3>
          </div>
          <div className="flex items-center gap-2">
            {category.summary?.status && (
              <Badge
                variant="outline"
                className="border-black/[0.08] bg-white text-xs text-[#86868b]"
              >
                {category.summary.status}
              </Badge>
            )}
            <StatusPill status={category.status} />
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs text-[#86868b]">
          <span>{refCount} refs</span>
          <span>{category.toolCalls.length} tool calls</span>
          <span>{steps.length} internal ops</span>
          <span>
            {findingCount} finding{findingCount === 1 ? "" : "s"}
          </span>
        </div>
      </header>

      {findingCount > 0 && (
        <section id="cat-findings" className="mt-5 scroll-mt-4">
          <Task defaultOpen>
            <TaskTrigger
              title={`Rule findings (${findingCount})`}
              className="border-black/[0.08]"
            />
            <TaskContent>
              {category.findings.map((finding, i) => (
                <TaskItem key={`${finding.rule_id}-${i}`}>
                  <div className="flex items-start gap-2">
                    <FindingIcon status={finding.status} />
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-medium text-[#86868b]">
                        Rule {finding.rule_id || "—"} · {finding.status}
                      </div>
                      {finding.detail && (
                        <div className="prose prose-neutral mt-1 max-w-none text-sm leading-relaxed text-[#1d1d1f]">
                          <MessageResponse parseIncompleteMarkdown={false}>
                            {finding.detail}
                          </MessageResponse>
                        </div>
                      )}
                    </div>
                  </div>
                </TaskItem>
              ))}
            </TaskContent>
          </Task>
        </section>
      )}

      {(category.tokens || steps.length > 0) && (
        <section id="cat-thinking" className="mt-5 scroll-mt-4 space-y-4">
          {steps.length > 0 && (
            <ChainOfThought defaultOpen={isRunning}>
              <ChainOfThoughtHeader>
                Evaluator steps ({steps.length})
                {isRunning && (
                  <Loader2 className="ml-2 inline size-3 animate-spin" />
                )}
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

          {category.tokens && (
            <Reasoning isStreaming={isRunning} defaultOpen>
              <ReasoningTrigger />
              <ReasoningContent>{category.tokens}</ReasoningContent>
            </Reasoning>
          )}
        </section>
      )}

      {category.toolCalls.length > 0 && (
        <section id="cat-tools" className="mt-5 scroll-mt-4">
          <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-[#86868b]">
            Tool calls ({category.toolCalls.length})
          </div>
          <div className="space-y-2">
            {category.toolCalls.map((tc) => {
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
        </section>
      )}

      {category.summary?.summary && (
        <section
          id="cat-summary"
          className="mt-5 scroll-mt-4 rounded-lg border border-black/[0.08] bg-white/60 p-4"
        >
          <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-[#86868b]">
            Category Summary
          </div>
          <div className="prose prose-neutral max-w-none text-sm leading-relaxed text-[#1d1d1f]">
            <MessageResponse parseIncompleteMarkdown={false}>
              {category.summary.summary}
            </MessageResponse>
          </div>
        </section>
      )}
    </>
  )

  if (bare) return <div className="space-y-0">{body}</div>

  return (
    <Message from="assistant" className="max-w-full">
      <MessageContent className="gap-0">{body}</MessageContent>
    </Message>
  )
}

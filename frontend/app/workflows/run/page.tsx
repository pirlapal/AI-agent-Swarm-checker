import { Suspense } from "react"

import { WorkflowRunShell } from "@/components/workflows/workflow-run-shell"

export default function WorkflowRunPage() {
  return (
    <Suspense fallback={null}>
      <WorkflowRunShell />
    </Suspense>
  )
}

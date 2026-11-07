import { WorkflowEditor } from "@/components/workflows/workflow-editor"

interface Props {
  params: Promise<{ id: string }>
}

export default async function EditWorkflowPage({ params }: Props) {
  const { id } = await params
  return <WorkflowEditor workflowId={id} />
}

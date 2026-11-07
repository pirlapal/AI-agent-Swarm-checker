/**
 * API service layer for the AI Agent Swarm backend.
 *
 * Two base URLs are used because the backend exposes the workflow / case
 * CRUD + upload endpoints on one API Gateway (`AiAgentBackendSwarmStack`)
 * and the `/caseWsPresign` endpoint on a separate one (`SwarmAgentCoreStack`).
 *
 *   NEXT_PUBLIC_API_BASE_URL            -> ApiUrl output of the main stack
 *   NEXT_PUBLIC_WS_PRESIGN_API_BASE_URL -> SwarmAgentCoreApiGatewayUrl output
 *
 * If the second variable is unset we fall back to the main one so local
 * development against a single Gateway keeps working.
 */

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, "")
const WS_PRESIGN_API = (
  process.env.NEXT_PUBLIC_WS_PRESIGN_API_BASE_URL || API_BASE
).replace(/\/$/, "")

// ─── Types ───

export interface ApiWorkflow {
  workflow_id: string
  name: string
  owner_id: string
  version: number
  created_at: number
  updated_at: number
  definition: {
    categories: ApiCategory[]
  }
  PK?: string
  SK?: string
  GSI1PK?: string
  GSI1SK?: string
}

export interface ApiCategory {
  category_id: string
  name: string
  rules: ApiRule[]
}

export interface ApiRule {
  rule_id: string
  name: string
  config: string
}

export interface ListWorkflowsResponse {
  items: ApiWorkflow[]
  count: number
  next_token: string | null
}

export interface CreateWorkflowPayload {
  name: string
  "owner-id"?: string
  definition?: {
    categories: {
      name: string
      category_id?: string
      rules: { name: string; rule_id?: string; config?: Record<string, unknown> }[]
    }[]
  }
}

export interface UpdateWorkflowPayload {
  version: number
  name?: string
  definition?: CreateWorkflowPayload["definition"]
}

export interface PresignPayload {
  "workflow-id": string
  kind: "case" | "ref"
  "name-of-files": string[]
  "case-id"?: string
  "category-id"?: string
}

export interface PresignedUrl {
  object_Id: string
  url: { url: string; fields: Record<string, string> }
}

export interface StartCasePayload {
  user_prompt: string
  case_file_names?: string[]
  owner_id?: string
}

export interface StartCaseResponse {
  case_id: string
  workflow_id: string
  status: string
  case_files: { s3_key: string; filename: string }[]
}

export interface CaseWsPresignPayload {
  workflow_id: string
  case_id: string
  user_id?: string
}

export interface CaseWsPresignResponse {
  url: string
  expires_in: number
  session_id: string
}

// ─── Helpers ───

export class ApiError extends Error {
  constructor(public status: number, public body: any) {
    super(body?.error || `API error ${status}`)
    this.name = "ApiError"
  }
}

async function request<T>(
  base: string,
  path: string,
  init?: RequestInit,
): Promise<T> {
  if (!base) throw new Error("Backend is not configured. Set the API URLs in .env.local to use live workflows.")
  const url = `${base}${path}`
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  })
  const data = await res.json()
  if (!res.ok) throw new ApiError(res.status, data)
  return data as T
}

// ─── Workflow CRUD ───

export async function listWorkflows(
  ownerId = "default",
  limit = 25,
  nextToken?: string,
): Promise<ListWorkflowsResponse> {
  const params = new URLSearchParams({
    "owner-id": ownerId,
    limit: String(limit),
  })
  if (nextToken) params.set("next-token", nextToken)
  return request<ListWorkflowsResponse>(API_BASE, `/workflows?${params}`)
}

export async function getWorkflow(id: string): Promise<ApiWorkflow> {
  return request<ApiWorkflow>(API_BASE, `/workflows/${id}`)
}

export async function createWorkflow(
  payload: CreateWorkflowPayload,
): Promise<{ workflow_id: string; version: number }> {
  return request(API_BASE, `/workflows`, {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function updateWorkflow(
  id: string,
  payload: UpdateWorkflowPayload,
): Promise<{ workflow_id: string; version: number }> {
  return request(API_BASE, `/workflows/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}

export async function deleteWorkflow(
  id: string,
): Promise<{ workflow_id: string; deleted: boolean }> {
  return request(API_BASE, `/workflows/${id}`, { method: "DELETE" })
}

// ─── Category ───

export async function addCategory(
  workflowId: string,
  payload: {
    version: number
    name: string
    rules?: { name: string; config?: Record<string, unknown> }[]
  },
) {
  return request<{ workflow_id: string; category_id: string; version: number }>(
    API_BASE,
    `/workflows/${workflowId}/categories`,
    { method: "POST", body: JSON.stringify(payload) },
  )
}

export async function updateCategory(
  workflowId: string,
  catId: string,
  payload: { version: number; name: string },
) {
  return request<{ workflow_id: string; category_id: string; version: number }>(
    API_BASE,
    `/workflows/${workflowId}/categories/${catId}`,
    { method: "PUT", body: JSON.stringify(payload) },
  )
}

export async function deleteCategoryApi(
  workflowId: string,
  catId: string,
  version: number,
) {
  return request<{
    workflow_id: string
    category_id: string
    deleted: boolean
    version: number
  }>(
    API_BASE,
    `/workflows/${workflowId}/categories/${catId}?version=${version}`,
    { method: "DELETE" },
  )
}

// ─── Rules ───

export async function addRule(
  workflowId: string,
  catId: string,
  payload: {
    version: number
    name: string
    config?: Record<string, unknown>
  },
) {
  return request<{
    workflow_id: string
    category_id: string
    rule_id: string
    version: number
  }>(
    API_BASE,
    `/workflows/${workflowId}/categories/${catId}/rules`,
    { method: "POST", body: JSON.stringify(payload) },
  )
}

export async function updateRule(
  workflowId: string,
  catId: string,
  ruleId: string,
  payload: {
    version: number
    name?: string
    config?: Record<string, unknown>
  },
) {
  return request<{
    workflow_id: string
    category_id: string
    rule_id: string
    version: number
  }>(
    API_BASE,
    `/workflows/${workflowId}/categories/${catId}/rules/${ruleId}`,
    { method: "PUT", body: JSON.stringify(payload) },
  )
}

export async function deleteRule(
  workflowId: string,
  catId: string,
  ruleId: string,
  version: number,
) {
  return request<{
    workflow_id: string
    category_id: string
    rule_id: string
    deleted: boolean
    version: number
  }>(
    API_BASE,
    `/workflows/${workflowId}/categories/${catId}/rules/${ruleId}?version=${version}`,
    { method: "DELETE" },
  )
}

// ─── File Uploads ───

export async function getPresignedUrls(
  payload: PresignPayload,
): Promise<PresignedUrl[]> {
  return request<PresignedUrl[]>(API_BASE, `/uploads/presign`, {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

/** Upload a file using the presigned POST data from S3. */
export async function uploadFileToS3(
  presigned: PresignedUrl,
  file: File,
): Promise<void> {
  const formData = new FormData()
  Object.entries(presigned.url.fields).forEach(([k, v]) =>
    formData.append(k, v),
  )
  formData.append("file", file)
  const res = await fetch(presigned.url.url, {
    method: "POST",
    body: formData,
  })
  if (!res.ok && res.status !== 204)
    throw new Error(`S3 upload failed: ${res.status}`)
}

// ─── Cases ───

export async function startCase(
  workflowId: string,
  payload: StartCasePayload,
): Promise<StartCaseResponse> {
  return request<StartCaseResponse>(
    API_BASE,
    `/workflows/${workflowId}/cases`,
    { method: "POST", body: JSON.stringify(payload) },
  )
}

export async function getCaseWsPresignedUrl(
  payload: CaseWsPresignPayload,
): Promise<CaseWsPresignResponse> {
  return request<CaseWsPresignResponse>(WS_PRESIGN_API, `/caseWsPresign`, {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

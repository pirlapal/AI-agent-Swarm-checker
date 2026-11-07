/**
 * localStorage-backed "recent runs" history. Mirrors what the ref frontend
 * did so the Run page can show a small history sidebar without needing a
 * server-side endpoint.
 */

const KEY = "swarm.run.history.v1"
const MAX = 20

export interface RunHistoryEntry {
  id: string
  caseId: string
  workflowId: string
  workflowName?: string
  prompt: string
  createdAt: number
  caseFiles: string[]
}

export function loadRunHistory(): RunHistoryEntry[] {
  if (typeof window === "undefined") return []
  try {
    const raw = window.localStorage.getItem(KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as RunHistoryEntry[]) : []
  } catch {
    return []
  }
}

export function saveRunHistoryEntry(entry: RunHistoryEntry) {
  if (typeof window === "undefined") return
  const current = loadRunHistory()
  const next = [entry, ...current.filter((e) => e.id !== entry.id)].slice(0, MAX)
  window.localStorage.setItem(KEY, JSON.stringify(next))
}

export function clearRunHistory() {
  if (typeof window === "undefined") return
  window.localStorage.removeItem(KEY)
}

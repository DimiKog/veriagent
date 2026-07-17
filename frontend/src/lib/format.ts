import { ApiError } from '../api/client'
import type { EventLifecycleStatusResponse, WorkflowState } from '../types'

export function formatJson(data: unknown): string {
  return JSON.stringify(data, null, 2)
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.displayMessage
  if (error instanceof Error) return error.message
  return 'An unexpected error occurred'
}

export function truncateHash(value: string): string {
  if (value.length <= 20) return value
  return `${value.slice(0, 8)}…${value.slice(-6)}`
}

export function formatAnchoredAt(unixSeconds: number | null | undefined): string {
  if (unixSeconds === null || unixSeconds === undefined) return ''
  try {
    return new Date(unixSeconds * 1000).toISOString()
  } catch {
    return String(unixSeconds)
  }
}

export function lifecyclePhaseFromStatus(
  status: EventLifecycleStatusResponse | null,
  hasSubmittedEvent: boolean,
): 'submitted' | 'batched' | 'anchored' | null {
  if (!hasSubmittedEvent && !status) return null
  if (status?.anchored) return 'anchored'
  if (status?.batched) return 'batched'
  if (hasSubmittedEvent || status) return 'submitted'
  return null
}

export function workflowPatchFromLifecycle(
  status: EventLifecycleStatusResponse,
): Partial<WorkflowState> {
  const patch: Partial<WorkflowState> = {
    event_id: status.event_id,
    event_hash: status.event_hash,
  }
  if (status.batch_id) patch.batch_id = status.batch_id
  if (status.merkle_root) patch.merkle_root = status.merkle_root
  if (status.tx_hash) patch.tx_hash = status.tx_hash
  if (status.chain_id !== null && status.chain_id !== undefined) {
    patch.chain_id = String(status.chain_id)
  }
  if (status.block_number !== null && status.block_number !== undefined) {
    patch.block_number = String(status.block_number)
  }
  if (status.anchored_at !== null && status.anchored_at !== undefined) {
    patch.anchored_at = formatAnchoredAt(status.anchored_at)
  }
  return patch
}

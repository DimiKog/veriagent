export interface AuditEvent {
  event_id: string
  agent_id: string
  task_id: string
  model_name: string
  tool_calls: string[]
  input_hash: string
  output_hash: string
  policy_version: string
  timestamp: string
  metadata?: Record<string, unknown> | null
}

export interface HealthResponse {
  status: string
  service: string
  version: string
}

export interface IngestionReceipt {
  event_id: string
  event_hash: string
  created_at: string
  signature: string
  algorithm: string
}

export interface StoreEventResponse {
  event_id: string
  event_hash: string
  created_at: string
  receipt: IngestionReceipt
}

export interface BatchResponse {
  batch_id: string
  merkle_root: string
  event_count: number
  created_at: string
  event_hashes: string[]
}

export interface MerkleProofStep {
  sibling: string
  side: 'left' | 'right'
}

export interface BatchProofResponse {
  batch_id: string
  event_id: string
  event_hash: string
  merkle_root: string
  proof: MerkleProofStep[]
}

export interface MerkleVerifyResponse {
  event_hash: string
  merkle_root: string
  verified: boolean
}

export interface BatchAnchorRecord {
  batch_id: string
  anchor_address: string
  tx_hash: string
  block_number: number
  anchored_at: number
  anchored_by: string
  chain_id: number
}

export interface AnchorBatchResponse extends BatchAnchorRecord {
  already_anchored: boolean
}

export interface WorkflowState {
  event_id: string
  event_hash: string
  batch_id: string
  merkle_root: string
  tx_hash: string
  chain_id: string
}

export const emptyWorkflowState = (): WorkflowState => ({
  event_id: '',
  event_hash: '',
  batch_id: '',
  merkle_root: '',
  tx_hash: '',
  chain_id: '',
})

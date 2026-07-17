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

export interface SignedAuditEvent extends AuditEvent {
  verification_method: string
  signature: string
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

/** Response from GET /audit/events/{event_id}/status */
export interface EventLifecycleStatusResponse {
  event_id: string
  event_hash: string
  created_at: string
  batched: boolean
  batch_id: string | null
  merkle_root: string | null
  anchored: boolean
  tx_hash: string | null
  block_number: number | null
  chain_id: number | null
  anchored_at: number | null
  anchored_by: string | null
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
  merkle_root: string
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
  block_number: string
  anchored_at: string
}

export const emptyWorkflowState = (): WorkflowState => ({
  event_id: '',
  event_hash: '',
  batch_id: '',
  merkle_root: '',
  tx_hash: '',
  chain_id: '',
  block_number: '',
  anchored_at: '',
})

/* ── Registration ─────────────────────────────────────── */

export interface CreateRegistrationRequest {
  agent_did: string
  agent_name: string
  agent_type: string
  description?: string | null
  verification_method: string
  public_key: string
  organization_name: string
  contact_email: string
  use_case_summary: string
}

export interface RegistrationProofPayload {
  purpose: string
  request_id: string
  agent_did: string
  nonce: string
  issued_at: string
  expires_at: string
}

export interface CreateRegistrationRequestResponse {
  request_id: string
  agent_did: string
  challenge_nonce: string
  challenge_expires_at: string
  proof_payload: RegistrationProofPayload
}

export interface RegistrationRequestStatusResponse {
  request_id: string
  status: string
  agent_did: string
  created_at: string
  challenge_expires_at: string | null
  proof_submitted_at: string | null
  reviewed_at: string | null
  credentials_available: boolean
  credentials_claimed: boolean
  credentials_claimed_at: string | null
  proof_payload: RegistrationProofPayload | null
}

export interface AdminRegistrationRequestSummary {
  request_id: string
  agent_did: string
  agent_name: string
  agent_type: string
  description: string | null
  organization_name: string
  contact_email: string
  use_case_summary: string
  status: string
  verification_method: string
  public_key: string
  challenge_expires_at: string
  proof_submitted_at: string | null
  reviewed_by: string | null
  reviewed_at: string | null
  review_notes: string | null
  approved_agent_did: string | null
  created_at: string
  updated_at: string
}

export interface AdminRegistrationRequestListResponse {
  requests: AdminRegistrationRequestSummary[]
}

export interface RegistrationRequestReviewBody {
  review_notes?: string | null
}

export interface ApproveRegistrationRequestResponse {
  request_id: string
  status: string
  agent_did: string
  agent_name: string
  agent_type: string
  description: string | null
  verification_method: string
  public_key: string
  agent_status: string
  created_at: string
  reviewed_at: string
  review_notes: string | null
  approved_agent_did: string
  /** One-time retrieval token. Agent API key is only available via credentials claim. */
  retrieval_token: string
}

export interface RejectRegistrationRequestResponse {
  request_id: string
  status: string
  agent_did: string
  reviewed_at: string
  reviewed_by: string
  review_notes: string | null
}

/* ── Agent event list ─────────────────────────────────── */

export interface AgentAuditEventSummary {
  event_id: string
  event_hash: string
  created_at: string
  batched: boolean
  anchored: boolean
}

export interface AgentAuditEventListResponse {
  events: AgentAuditEventSummary[]
}

/* ── Ops ──────────────────────────────────────────────── */

export type AutoAnchorLastStatus =
  | 'idle'
  | 'no_events'
  | 'below_threshold'
  | 'batch_created'
  | 'anchor_succeeded'
  | 'anchor_failed'

export interface OpsStatusResponse {
  service: string
  version: string
  auto_anchor_enabled: boolean
  interval_seconds: number
  min_events: number
  scheduler_running: boolean
  last_run_at: string | null
  last_status: AutoAnchorLastStatus
  last_batch_id: string | null
  last_anchor_tx: string | null
  last_error: string | null
}

/* ── UI helpers ───────────────────────────────────────── */

export type SectionStatus =
  | { kind: 'idle' }
  | { kind: 'loading'; message: string }
  | { kind: 'success'; message: string; data?: unknown }
  | { kind: 'error'; message: string }

export type LifecyclePhase = 'submitted' | 'batched' | 'anchored'

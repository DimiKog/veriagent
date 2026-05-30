import { useCallback, useState } from 'react'
import {
  anchorBatch,
  ApiError,
  BLOCKSCOUT_CONFIGURED,
  BLOCKSCOUT_TX_BASE,
  createBatch,
  getBatchAnchor,
  getBatchProof,
  getHealth,
  storeAuditEvent,
  verifyMerkleProof,
} from './api/client'
import type {
  AnchorBatchResponse,
  AuditEvent,
  BatchProofResponse,
  BatchResponse,
  HealthResponse,
  MerkleProofStep,
  StoreEventResponse,
  WorkflowState,
} from './types'
import { emptyWorkflowState } from './types'
import './App.css'

/* ── Types ───────────────────────────────────────────── */

type SectionStatus =
  | { kind: 'idle' }
  | { kind: 'loading'; message: string }
  | { kind: 'success'; message: string; data?: unknown }
  | { kind: 'error'; message: string }

/* ── Helpers ─────────────────────────────────────────── */

function defaultEventPayload(): AuditEvent {
  const suffix = Date.now()
  return {
    event_id: `event-${suffix}`,
    agent_id: 'agent-001',
    task_id: 'task-001',
    model_name: 'demo-model',
    tool_calls: ['search', 'calculator'],
    input_hash: 'sha256:input123',
    output_hash: 'sha256:output456',
    policy_version: 'policy-v0.1',
    timestamp: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
    metadata: { purpose: 'dashboard-demo' },
  }
}

function formatJson(data: unknown): string {
  return JSON.stringify(data, null, 2)
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.displayMessage
  if (error instanceof Error) return error.message
  return 'An unexpected error occurred'
}

function truncateHash(value: string): string {
  if (value.length <= 20) return value
  return `${value.slice(0, 8)}…${value.slice(-6)}`
}

/* ── Sub-components ──────────────────────────────────── */

function ShieldIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  )
}

function ExternalLinkIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  )
}

function StatusBox({ status }: { status: SectionStatus }) {
  if (status.kind === 'idle') return null

  const className =
    status.kind === 'loading'
      ? 'status status--loading'
      : status.kind === 'success'
        ? 'status status--success'
        : 'status status--error'

  const icon =
    status.kind === 'loading' ? (
      <em className="status__icon status__icon--spin" aria-hidden="true">↻</em>
    ) : status.kind === 'success' ? (
      <em className="status__icon" aria-hidden="true">✓</em>
    ) : (
      <em className="status__icon" aria-hidden="true">✕</em>
    )

  return (
    <div className={className} role="status">
      <div className="status__message">
        {icon}
        <span>{status.message}</span>
      </div>
      {status.kind === 'success' && status.data !== undefined && (
        <pre>{formatJson(status.data)}</pre>
      )}
    </div>
  )
}

function HashValue({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)

  if (!value) {
    return <span className="hash-value__empty">—</span>
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }).catch(() => {/* clipboard unavailable */})
  }

  return (
    <div className="hash-value">
      <span className="hash-value__text" title={value}>
        {truncateHash(value)}
      </span>
      <button
        type="button"
        className={`hash-value__copy${copied ? ' hash-value__copy--copied' : ''}`}
        onClick={handleCopy}
        title={copied ? 'Copied!' : 'Copy to clipboard'}
      >
        {copied ? '✓' : '⎘'}
      </button>
    </div>
  )
}

/* ── App ─────────────────────────────────────────────── */

function App() {
  const [workflow, setWorkflow] = useState<WorkflowState>(emptyWorkflowState)
  const [eventForm, setEventForm] = useState<AuditEvent>(defaultEventPayload)
  const [metadataText, setMetadataText] = useState(
    () => JSON.stringify(defaultEventPayload().metadata, null, 2),
  )

  const [healthStatus, setHealthStatus] = useState<SectionStatus>({ kind: 'idle' })
  const [eventStatus, setEventStatus] = useState<SectionStatus>({ kind: 'idle' })
  const [batchStatus, setBatchStatus] = useState<SectionStatus>({ kind: 'idle' })
  const [proofStatus, setProofStatus] = useState<SectionStatus>({ kind: 'idle' })
  const [anchorStatus, setAnchorStatus] = useState<SectionStatus>({ kind: 'idle' })
  const [anchorResultStatus, setAnchorResultStatus] = useState<SectionStatus>({ kind: 'idle' })

  const [lastProof, setLastProof] = useState<MerkleProofStep[]>([])

  const updateWorkflow = useCallback((patch: Partial<WorkflowState>) => {
    setWorkflow((current) => ({ ...current, ...patch }))
  }, [])

  /* ── Handlers ── */

  const handleHealthCheck = async () => {
    setHealthStatus({ kind: 'loading', message: 'Checking API health…' })
    try {
      const data: HealthResponse = await getHealth()
      setHealthStatus({
        kind: 'success',
        message: `API is healthy — ${data.service} v${data.version}`,
        data,
      })
    } catch (error) {
      setHealthStatus({ kind: 'error', message: errorMessage(error) })
    }
  }

  const handleCreateEvent = async () => {
    setEventStatus({ kind: 'loading', message: 'Storing audit event…' })
    try {
      let metadata: Record<string, unknown> | null = null
      try {
        metadata = JSON.parse(metadataText) as Record<string, unknown>
      } catch {
        setEventStatus({
          kind: 'error',
          message: 'Metadata must be valid JSON before storing the event.',
        })
        return
      }

      const data: StoreEventResponse = await storeAuditEvent({ ...eventForm, metadata })
      updateWorkflow({ event_id: data.event_id, event_hash: data.event_hash })
      setEventStatus({ kind: 'success', message: 'Audit event stored successfully.', data })
      const nextEvent = defaultEventPayload()
      setEventForm(nextEvent)
      setMetadataText(JSON.stringify(nextEvent.metadata, null, 2))
    } catch (error) {
      setEventStatus({ kind: 'error', message: errorMessage(error) })
    }
  }

  const handleCreateBatch = async () => {
    setBatchStatus({ kind: 'loading', message: 'Creating Merkle batch…' })
    try {
      const data: BatchResponse = await createBatch()
      updateWorkflow({ batch_id: data.batch_id, merkle_root: data.merkle_root })
      setBatchStatus({
        kind: 'success',
        message: `Batch created with ${data.event_count} event(s).`,
        data,
      })
    } catch (error) {
      setBatchStatus({ kind: 'error', message: errorMessage(error) })
    }
  }

  const handleRetrieveProof = async () => {
    if (!workflow.batch_id || !workflow.event_id) {
      setProofStatus({
        kind: 'error',
        message: 'Create an event and batch first so batch_id and event_id are set.',
      })
      return
    }

    setProofStatus({ kind: 'loading', message: 'Fetching Merkle proof…' })
    try {
      const data: BatchProofResponse = await getBatchProof(workflow.batch_id, workflow.event_id)
      setLastProof(data.proof)
      updateWorkflow({ event_hash: data.event_hash, merkle_root: data.merkle_root })

      const verifyResult = await verifyMerkleProof({
        event_hash: data.event_hash,
        merkle_root: data.merkle_root,
        proof: data.proof,
      })

      setProofStatus({
        kind: 'success',
        message: verifyResult.verified
          ? 'Merkle proof retrieved and verified successfully.'
          : 'Merkle proof retrieved, but verification returned false.',
        data: { proof: data, verify: verifyResult },
      })
    } catch (error) {
      setProofStatus({ kind: 'error', message: errorMessage(error) })
    }
  }

  const handleAnchorBatch = async () => {
    if (!workflow.batch_id) {
      setAnchorStatus({ kind: 'error', message: 'Create a Merkle batch first.' })
      return
    }

    setAnchorStatus({ kind: 'loading', message: 'Submitting anchor transaction…' })
    try {
      const data: AnchorBatchResponse = await anchorBatch(workflow.batch_id)
      updateWorkflow({ tx_hash: data.tx_hash, chain_id: String(data.chain_id) })
      setAnchorStatus({
        kind: 'success',
        message: data.already_anchored
          ? 'Batch was already anchored on chain.'
          : 'Batch anchored on chain successfully.',
        data,
      })
    } catch (error) {
      setAnchorStatus({ kind: 'error', message: errorMessage(error) })
    }
  }

  const handleShowAnchorResult = async () => {
    if (!workflow.batch_id) {
      setAnchorResultStatus({ kind: 'error', message: 'Create and anchor a batch first.' })
      return
    }

    setAnchorResultStatus({ kind: 'loading', message: 'Fetching anchor record…' })
    try {
      const data = await getBatchAnchor(workflow.batch_id)
      updateWorkflow({ tx_hash: data.tx_hash, chain_id: String(data.chain_id) })
      setAnchorResultStatus({
        kind: 'success',
        message: 'Anchor record retrieved from the backend.',
        data,
      })
    } catch (error) {
      setAnchorResultStatus({ kind: 'error', message: errorMessage(error) })
    }
  }

  /* ── Render ── */

  return (
    <div className="dashboard">
      <header className="dashboard__header">
        <div className="dashboard__header-top">
          <div className="dashboard__logo" aria-hidden="true">
            <ShieldIcon />
          </div>
          <h1>
            VeriAgent
            <span className="dashboard__version">v0.7.0</span>
          </h1>
        </div>
        <p>
          Audit workflow UI — events, Merkle batches, proofs, and on-chain anchoring via the
          VeriAgent API.
        </p>
      </header>

      <div className="dashboard__layout">
        <div className="dashboard__sections">

          {/* Step 1 */}
          <section className="panel">
            <h2 className="panel__heading">
              <span className="step-badge" aria-label="Step 1">1</span>
              API health check
            </h2>
            <p>Verify connectivity to the deployed VeriAgent backend.</p>
            <div className="panel__actions">
              <button
                type="button"
                className="btn btn--primary"
                onClick={handleHealthCheck}
                disabled={healthStatus.kind === 'loading'}
              >
                {healthStatus.kind === 'loading' ? 'Checking…' : 'Check health'}
              </button>
            </div>
            <StatusBox status={healthStatus} />
          </section>

          {/* Step 2 */}
          <section className="panel">
            <h2 className="panel__heading">
              <span className="step-badge" aria-label="Step 2">2</span>
              Create audit event
            </h2>
            <p>Store a structured audit event and receive a signed ingestion receipt.</p>
            <div className="form-grid">
              <label>
                Event ID
                <input
                  value={eventForm.event_id}
                  onChange={(e) => setEventForm((c) => ({ ...c, event_id: e.target.value }))}
                />
              </label>
              <label>
                Agent ID
                <input
                  value={eventForm.agent_id}
                  onChange={(e) => setEventForm((c) => ({ ...c, agent_id: e.target.value }))}
                />
              </label>
              <label>
                Task ID
                <input
                  value={eventForm.task_id}
                  onChange={(e) => setEventForm((c) => ({ ...c, task_id: e.target.value }))}
                />
              </label>
              <label>
                Model name
                <input
                  value={eventForm.model_name}
                  onChange={(e) => setEventForm((c) => ({ ...c, model_name: e.target.value }))}
                />
              </label>
              <label>
                Tool calls (comma-separated)
                <input
                  value={eventForm.tool_calls.join(', ')}
                  onChange={(e) =>
                    setEventForm((c) => ({
                      ...c,
                      tool_calls: e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
                    }))
                  }
                />
              </label>
              <label>
                Input hash
                <input
                  value={eventForm.input_hash}
                  onChange={(e) => setEventForm((c) => ({ ...c, input_hash: e.target.value }))}
                />
              </label>
              <label>
                Output hash
                <input
                  value={eventForm.output_hash}
                  onChange={(e) => setEventForm((c) => ({ ...c, output_hash: e.target.value }))}
                />
              </label>
              <label>
                Policy version
                <input
                  value={eventForm.policy_version}
                  onChange={(e) =>
                    setEventForm((c) => ({ ...c, policy_version: e.target.value }))
                  }
                />
              </label>
              <label>
                Timestamp (ISO 8601)
                <input
                  value={eventForm.timestamp}
                  onChange={(e) => setEventForm((c) => ({ ...c, timestamp: e.target.value }))}
                />
              </label>
              <label>
                Metadata (JSON)
                <textarea
                  value={metadataText}
                  onChange={(e) => setMetadataText(e.target.value)}
                />
              </label>
            </div>
            <div className="panel__actions">
              <button
                type="button"
                className="btn btn--primary"
                onClick={handleCreateEvent}
                disabled={eventStatus.kind === 'loading'}
              >
                {eventStatus.kind === 'loading' ? 'Storing…' : 'Store event'}
              </button>
            </div>
            <StatusBox status={eventStatus} />
          </section>

          {/* Step 3 */}
          <section className="panel">
            <h2 className="panel__heading">
              <span className="step-badge" aria-label="Step 3">3</span>
              Create Merkle batch
            </h2>
            <p>
              Batch all unbatched stored events into a Merkle tree and compute the root.
            </p>
            <div className="panel__actions">
              <button
                type="button"
                className="btn btn--primary"
                onClick={handleCreateBatch}
                disabled={batchStatus.kind === 'loading'}
              >
                {batchStatus.kind === 'loading' ? 'Creating…' : 'Create batch'}
              </button>
            </div>
            <StatusBox status={batchStatus} />
          </section>

          {/* Step 4 */}
          <section className="panel">
            <h2 className="panel__heading">
              <span className="step-badge" aria-label="Step 4">4</span>
              Retrieve Merkle proof
            </h2>
            <p>
              Fetch an inclusion proof for the current event in the current batch, then verify it
              with <code>POST /audit/merkle/verify</code>.
            </p>
            <div className="panel__actions">
              <button
                type="button"
                className="btn btn--primary"
                onClick={handleRetrieveProof}
                disabled={proofStatus.kind === 'loading'}
              >
                {proofStatus.kind === 'loading' ? 'Retrieving…' : 'Get & verify proof'}
              </button>
            </div>
            {lastProof.length > 0 && proofStatus.kind !== 'loading' && (
              <p style={{ marginTop: '0.65rem', marginBottom: 0 }}>
                Cached proof steps:{' '}
                <span className="badge badge--ok">{lastProof.length}</span>
              </p>
            )}
            <StatusBox status={proofStatus} />
          </section>

          {/* Step 5 */}
          <section className="panel">
            <h2 className="panel__heading">
              <span className="step-badge" aria-label="Step 5">5</span>
              Anchor batch
            </h2>
            <p>
              Submit the current batch Merkle root to the on-chain anchor contract. Signing is
              handled server-side — this UI never handles private keys or secrets.
            </p>
            <div className="panel__actions">
              <button
                type="button"
                className="btn btn--primary"
                onClick={handleAnchorBatch}
                disabled={anchorStatus.kind === 'loading'}
              >
                {anchorStatus.kind === 'loading' ? 'Anchoring…' : 'Anchor batch'}
              </button>
            </div>
            <StatusBox status={anchorStatus} />
          </section>

          {/* Step 6 */}
          <section className="panel">
            <h2 className="panel__heading">
              <span className="step-badge" aria-label="Step 6">6</span>
              Show anchor result
            </h2>
            <p>Load the stored anchor record for the current batch from the backend.</p>
            <div className="panel__actions">
              <button
                type="button"
                className="btn btn--primary"
                onClick={handleShowAnchorResult}
                disabled={anchorResultStatus.kind === 'loading'}
              >
                {anchorResultStatus.kind === 'loading' ? 'Loading…' : 'Get anchor record'}
              </button>
            </div>
            <StatusBox status={anchorResultStatus} />
          </section>

        </div>

        {/* Workflow sidebar */}
        <aside className="panel workflow-panel">
          <h2 className="panel__heading">Current workflow state</h2>
          <dl className="workflow-list">
            <div>
              <dt>event_id</dt>
              <HashValue value={workflow.event_id} />
            </div>
            <div>
              <dt>event_hash</dt>
              <HashValue value={workflow.event_hash} />
            </div>
            <div>
              <dt>batch_id</dt>
              <HashValue value={workflow.batch_id} />
            </div>
            <div>
              <dt>merkle_root</dt>
              <HashValue value={workflow.merkle_root} />
            </div>
            <div>
              <dt>tx_hash</dt>
              <HashValue value={workflow.tx_hash} />
            </div>
            <div>
              <dt>chain_id</dt>
              <HashValue value={workflow.chain_id} />
            </div>
          </dl>
          {workflow.tx_hash && BLOCKSCOUT_CONFIGURED && (
            <a
              className="external-link"
              href={`${BLOCKSCOUT_TX_BASE}${workflow.tx_hash}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              View on Blockscout
              <ExternalLinkIcon />
            </a>
          )}
        </aside>
      </div>
    </div>
  )
}

export default App

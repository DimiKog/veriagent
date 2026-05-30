import { useCallback, useState } from 'react'
import {
  anchorBatch,
  ApiError,
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

type SectionStatus =
  | { kind: 'idle' }
  | { kind: 'loading'; message: string }
  | { kind: 'success'; message: string; data?: unknown }
  | { kind: 'error'; message: string }

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
  if (error instanceof ApiError) {
    return error.displayMessage
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'An unexpected error occurred'
}

function StatusBox({ status }: { status: SectionStatus }) {
  if (status.kind === 'idle') {
    return null
  }

  const className =
    status.kind === 'loading'
      ? 'status status--loading'
      : status.kind === 'success'
        ? 'status status--success'
        : 'status status--error'

  return (
    <div className={className} role="status">
      <div>{status.message}</div>
      {status.kind === 'success' && status.data !== undefined && (
        <pre>{formatJson(status.data)}</pre>
      )}
    </div>
  )
}

function WorkflowValue({ value }: { value: string }) {
  if (!value) {
    return <dd className="empty">—</dd>
  }
  return <dd>{value}</dd>
}

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
  const [anchorResultStatus, setAnchorResultStatus] = useState<SectionStatus>({
    kind: 'idle',
  })

  const [lastProof, setLastProof] = useState<MerkleProofStep[]>([])

  const updateWorkflow = useCallback((patch: Partial<WorkflowState>) => {
    setWorkflow((current) => ({ ...current, ...patch }))
  }, [])

  const handleHealthCheck = async () => {
    setHealthStatus({ kind: 'loading', message: 'Checking API health…' })
    try {
      const data: HealthResponse = await getHealth()
      setHealthStatus({
        kind: 'success',
        message: `API is healthy (${data.service} v${data.version})`,
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

      const data: StoreEventResponse = await storeAuditEvent({
        ...eventForm,
        metadata,
      })
      updateWorkflow({
        event_id: data.event_id,
        event_hash: data.event_hash,
      })
      setEventStatus({
        kind: 'success',
        message: 'Audit event stored successfully.',
        data,
      })
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
      updateWorkflow({
        batch_id: data.batch_id,
        merkle_root: data.merkle_root,
      })
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
      const data: BatchProofResponse = await getBatchProof(
        workflow.batch_id,
        workflow.event_id,
      )
      setLastProof(data.proof)
      updateWorkflow({
        event_hash: data.event_hash,
        merkle_root: data.merkle_root,
      })

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
      setAnchorStatus({
        kind: 'error',
        message: 'Create a Merkle batch first so batch_id is set.',
      })
      return
    }

    setAnchorStatus({ kind: 'loading', message: 'Submitting anchor transaction…' })
    try {
      const data: AnchorBatchResponse = await anchorBatch(workflow.batch_id)
      updateWorkflow({
        tx_hash: data.tx_hash,
        chain_id: String(data.chain_id),
      })
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
      setAnchorResultStatus({
        kind: 'error',
        message: 'Create and anchor a batch first so batch_id is set.',
      })
      return
    }

    setAnchorResultStatus({ kind: 'loading', message: 'Fetching anchor record…' })
    try {
      const data = await getBatchAnchor(workflow.batch_id)
      updateWorkflow({
        tx_hash: data.tx_hash,
        chain_id: String(data.chain_id),
      })
      setAnchorResultStatus({
        kind: 'success',
        message: 'Anchor record retrieved from the backend.',
        data,
      })
    } catch (error) {
      setAnchorResultStatus({ kind: 'error', message: errorMessage(error) })
    }
  }

  const metadataJson = metadataText

  return (
    <div className="dashboard">
      <header className="dashboard__header">
        <h1>VeriAgent Dashboard</h1>
        <p>
          Minimal audit workflow UI — events, Merkle batches, proofs, and on-chain
          anchoring via the VeriAgent API.
        </p>
      </header>

      <div className="dashboard__layout">
        <div className="dashboard__sections">
          <section className="panel">
            <h2>API health check</h2>
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

          <section className="panel">
            <h2>Create audit event</h2>
            <p>Store a structured audit event and receive a signed ingestion receipt.</p>
            <div className="form-grid">
              <label>
                Event ID
                <input
                  value={eventForm.event_id}
                  onChange={(event) =>
                    setEventForm((current) => ({
                      ...current,
                      event_id: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                Agent ID
                <input
                  value={eventForm.agent_id}
                  onChange={(event) =>
                    setEventForm((current) => ({
                      ...current,
                      agent_id: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                Task ID
                <input
                  value={eventForm.task_id}
                  onChange={(event) =>
                    setEventForm((current) => ({
                      ...current,
                      task_id: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                Model name
                <input
                  value={eventForm.model_name}
                  onChange={(event) =>
                    setEventForm((current) => ({
                      ...current,
                      model_name: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                Tool calls (comma-separated)
                <input
                  value={eventForm.tool_calls.join(', ')}
                  onChange={(event) =>
                    setEventForm((current) => ({
                      ...current,
                      tool_calls: event.target.value
                        .split(',')
                        .map((item) => item.trim())
                        .filter(Boolean),
                    }))
                  }
                />
              </label>
              <label>
                Input hash
                <input
                  value={eventForm.input_hash}
                  onChange={(event) =>
                    setEventForm((current) => ({
                      ...current,
                      input_hash: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                Output hash
                <input
                  value={eventForm.output_hash}
                  onChange={(event) =>
                    setEventForm((current) => ({
                      ...current,
                      output_hash: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                Policy version
                <input
                  value={eventForm.policy_version}
                  onChange={(event) =>
                    setEventForm((current) => ({
                      ...current,
                      policy_version: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                Timestamp (ISO 8601)
                <input
                  value={eventForm.timestamp}
                  onChange={(event) =>
                    setEventForm((current) => ({
                      ...current,
                      timestamp: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                Metadata (JSON)
                <textarea
                  value={metadataJson}
                  onChange={(event) => setMetadataText(event.target.value)}
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

          <section className="panel">
            <h2>Create Merkle batch</h2>
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

          <section className="panel">
            <h2>Retrieve Merkle proof</h2>
            <p>
              Fetch an inclusion proof for the current event in the current batch, then
              verify it with <code>POST /audit/merkle/verify</code>.
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
              <p>
                Cached proof steps:{' '}
                <span className="badge badge--ok">{lastProof.length}</span>
              </p>
            )}
            <StatusBox status={proofStatus} />
          </section>

          <section className="panel">
            <h2>Anchor batch</h2>
            <p>
              Submit the current batch Merkle root to the on-chain anchor contract. Signing
              is handled server-side — this UI never handles private keys or secrets.
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

          <section className="panel">
            <h2>Show anchor result</h2>
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

        <aside className="panel workflow-panel">
          <h2>Current workflow state</h2>
          <dl className="workflow-list">
            <div>
              <dt>event_id</dt>
              <WorkflowValue value={workflow.event_id} />
            </div>
            <div>
              <dt>event_hash</dt>
              <WorkflowValue value={workflow.event_hash} />
            </div>
            <div>
              <dt>batch_id</dt>
              <WorkflowValue value={workflow.batch_id} />
            </div>
            <div>
              <dt>merkle_root</dt>
              <WorkflowValue value={workflow.merkle_root} />
            </div>
            <div>
              <dt>tx_hash</dt>
              <WorkflowValue value={workflow.tx_hash} />
            </div>
            <div>
              <dt>chain_id</dt>
              <WorkflowValue value={workflow.chain_id} />
            </div>
          </dl>
          {workflow.tx_hash && (
            <a
              className="external-link"
              href={`${BLOCKSCOUT_TX_BASE}${workflow.tx_hash}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              View transaction on Blockscout
            </a>
          )}
        </aside>
      </div>
    </div>
  )
}

export default App

import { useCallback, useState } from 'react'
import {
  API_DOCS_URL,
  ApiError,
  BLOCKSCOUT_CONFIGURED,
  BLOCKSCOUT_TX_BASE,
  formatStoreEventError,
  getBatch,
  getBatchAnchor,
  getBatchProof,
  getHealth,
  storeAuditEvent,
  verifyMerkleProof,
} from './api/client'
import type {
  AuditEvent,
  BatchProofResponse,
  BatchResponse,
  HealthResponse,
  MerkleProofStep,
  StoreEventResponse,
  WorkflowState,
} from './types'
import { emptyWorkflowState } from './types'
import { validateAgentCredentials } from './utils/credentials'
import { DidKeyError } from './utils/didKey'
import { signAuditEvent } from './utils/signEvent'
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
    agent_id: '',
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
  const [agentDid, setAgentDid] = useState('')
  const [agentApiKey, setAgentApiKey] = useState('')
  const [agentPrivateKey, setAgentPrivateKey] = useState('')
  const [agentVerificationMethod, setAgentVerificationMethod] = useState('')
  const [agentCredentialsReady, setAgentCredentialsReady] = useState(false)
  const [eventForm, setEventForm] = useState<AuditEvent>(defaultEventPayload)
  const [metadataText, setMetadataText] = useState(
    () => JSON.stringify(defaultEventPayload().metadata, null, 2),
  )

  const agentCredentialsFilled =
    agentDid.trim().length > 0 &&
    agentApiKey.trim().length > 0 &&
    agentPrivateKey.trim().length > 0

  const [healthStatus, setHealthStatus] = useState<SectionStatus>({ kind: 'idle' })
  const [credentialsStatus, setCredentialsStatus] = useState<SectionStatus>({ kind: 'idle' })
  const [eventStatus, setEventStatus] = useState<SectionStatus>({ kind: 'idle' })
  const [evidenceBatchStatus, setEvidenceBatchStatus] = useState<SectionStatus>({ kind: 'idle' })
  const [evidenceProofStatus, setEvidenceProofStatus] = useState<SectionStatus>({ kind: 'idle' })
  const [evidenceAnchorStatus, setEvidenceAnchorStatus] = useState<SectionStatus>({ kind: 'idle' })

  const [evidenceBatchId, setEvidenceBatchId] = useState('')
  const [evidenceEventId, setEvidenceEventId] = useState('')
  const [lastProof, setLastProof] = useState<MerkleProofStep[]>([])

  const updateWorkflow = useCallback((patch: Partial<WorkflowState>) => {
    setWorkflow((current) => ({ ...current, ...patch }))
  }, [])

  const handleAgentDidChange = (value: string) => {
    setAgentDid(value)
    setAgentCredentialsReady(false)
    setAgentVerificationMethod('')
    setCredentialsStatus({ kind: 'idle' })
  }

  const handleAgentApiKeyChange = (value: string) => {
    setAgentApiKey(value)
    setAgentCredentialsReady(false)
    setAgentVerificationMethod('')
    setCredentialsStatus({ kind: 'idle' })
  }

  const handleAgentPrivateKeyChange = (value: string) => {
    setAgentPrivateKey(value)
    setAgentCredentialsReady(false)
    setAgentVerificationMethod('')
    setCredentialsStatus({ kind: 'idle' })
  }

  const handleUseAgentCredentials = async () => {
    setCredentialsStatus({ kind: 'loading', message: 'Validating agent credentials…' })
    try {
      const { verificationMethod } = await validateAgentCredentials(
        agentDid,
        agentPrivateKey,
      )
      setAgentVerificationMethod(verificationMethod)
      setAgentCredentialsReady(true)
      setCredentialsStatus({
        kind: 'success',
        message: 'Agent credentials validated. DID and private key match.',
      })
    } catch (error) {
      setAgentCredentialsReady(false)
      setAgentVerificationMethod('')
      const message =
        error instanceof DidKeyError
          ? error.message
          : error instanceof Error
            ? error.message
            : 'Could not validate agent credentials.'
      setCredentialsStatus({ kind: 'error', message })
    }
  }

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
    if (!agentCredentialsReady) {
      setEventStatus({
        kind: 'error',
        message: 'Click "Use agent credentials" in step 2 before creating an audit event.',
      })
      return
    }

    setEventStatus({ kind: 'loading', message: 'Signing and storing audit event…' })
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

      const unsignedEvent: AuditEvent = {
        ...eventForm,
        agent_id: agentDid.trim(),
        metadata,
      }
      const signedEvent = await signAuditEvent(
        unsignedEvent,
        agentPrivateKey,
        agentVerificationMethod,
      )
      const data: StoreEventResponse = await storeAuditEvent(
        signedEvent,
        agentApiKey.trim(),
      )
      updateWorkflow({ event_id: data.event_id, event_hash: data.event_hash })
      setEvidenceEventId(data.event_id)
      setEventStatus({
        kind: 'success',
        message:
          'Event submitted. Batch creation and anchoring are operator-controlled in v0.9.6.',
        data,
      })
      const nextEvent = defaultEventPayload()
      setEventForm(nextEvent)
      setMetadataText(JSON.stringify(nextEvent.metadata, null, 2))
    } catch (error) {
      if (error instanceof DidKeyError) {
        setEventStatus({ kind: 'error', message: error.message })
        return
      }
      setEventStatus({ kind: 'error', message: formatStoreEventError(error) })
    }
  }

  const handleLookupBatch = async () => {
    const batchId = evidenceBatchId.trim()
    if (!batchId) {
      setEvidenceBatchStatus({
        kind: 'error',
        message: 'Enter a batch_id to look up batch metadata.',
      })
      return
    }

    setEvidenceBatchStatus({ kind: 'loading', message: 'Fetching batch metadata…' })
    try {
      const data: BatchResponse = await getBatch(batchId)
      updateWorkflow({ batch_id: data.batch_id, merkle_root: data.merkle_root })
      setEvidenceBatchStatus({
        kind: 'success',
        message: `Batch found with ${data.event_count} event(s).`,
        data,
      })
    } catch (error) {
      setEvidenceBatchStatus({ kind: 'error', message: errorMessage(error) })
    }
  }

  const handleRetrieveProof = async () => {
    const batchId = evidenceBatchId.trim()
    const eventId = evidenceEventId.trim()
    if (!batchId || !eventId) {
      setEvidenceProofStatus({
        kind: 'error',
        message: 'Enter both batch_id and event_id to retrieve a Merkle proof.',
      })
      return
    }

    setEvidenceProofStatus({ kind: 'loading', message: 'Fetching Merkle proof…' })
    try {
      const data: BatchProofResponse = await getBatchProof(batchId, eventId)
      setLastProof(data.proof)
      updateWorkflow({
        batch_id: data.batch_id,
        event_id: data.event_id,
        event_hash: data.event_hash,
        merkle_root: data.merkle_root,
      })

      const verifyResult = await verifyMerkleProof({
        event_hash: data.event_hash,
        merkle_root: data.merkle_root,
        proof: data.proof,
      })

      setEvidenceProofStatus({
        kind: 'success',
        message: verifyResult.verified
          ? 'Merkle proof retrieved and verified successfully.'
          : 'Merkle proof retrieved, but verification returned false.',
        data: { proof: data, verify: verifyResult },
      })
    } catch (error) {
      setEvidenceProofStatus({ kind: 'error', message: errorMessage(error) })
    }
  }

  const handleShowAnchorResult = async () => {
    const batchId = evidenceBatchId.trim()
    if (!batchId) {
      setEvidenceAnchorStatus({
        kind: 'error',
        message: 'Enter a batch_id to load the anchor record.',
      })
      return
    }

    setEvidenceAnchorStatus({ kind: 'loading', message: 'Fetching anchor record…' })
    try {
      const data = await getBatchAnchor(batchId)
      updateWorkflow({
        batch_id: data.batch_id,
        tx_hash: data.tx_hash,
        chain_id: String(data.chain_id),
      })
      setEvidenceAnchorStatus({
        kind: 'success',
        message: 'Anchor record retrieved from the backend.',
        data,
      })
    } catch (error) {
      setEvidenceAnchorStatus({ kind: 'error', message: errorMessage(error) })
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
            <span className="dashboard__version">v0.9.6</span>
          </h1>
          <nav className="dashboard__nav" aria-label="External links">
            <a href={API_DOCS_URL} target="_blank" rel="noopener noreferrer">
              API Docs
            </a>
            <span aria-hidden="true">·</span>
            <a
              href="https://github.com/DimiKog/veriagent"
              target="_blank"
              rel="noopener noreferrer"
            >
              GitHub
            </a>
            <span aria-hidden="true">·</span>
            <a
              href={`https://blockexplorer.dimikog.org/address/0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A`}
              target="_blank"
              rel="noopener noreferrer"
            >
              Contract
            </a>
          </nav>
        </div>
        <p className="dashboard__tagline">
          Audit events are hashed and committed on-chain — only cryptographic proofs are anchored
          to Besu Edu-Net, never raw data.
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
              Agent credentials
              {agentCredentialsReady && (
                <span className="badge badge--ok">Ready</span>
              )}
            </h2>
            <p className="panel__helper">
              Use a registered agent DID, agent API key, and demo private key. Registration is
              currently done through the admin API. The private key stays in memory for this page
              session only.
            </p>
            <div className="form-grid">
              <label>
                Agent DID
                <input
                  value={agentDid}
                  onChange={(e) => handleAgentDidChange(e.target.value)}
                  placeholder="did:key:z..."
                  autoComplete="off"
                  spellCheck={false}
                />
              </label>
              <label>
                Agent API Key
                <input
                  type="password"
                  value={agentApiKey}
                  onChange={(e) => handleAgentApiKeyChange(e.target.value)}
                  placeholder="va_agent_..."
                  autoComplete="off"
                  spellCheck={false}
                />
              </label>
              <label>
                Agent Private Key (base64, demo mode)
                <input
                  type="password"
                  value={agentPrivateKey}
                  onChange={(e) => handleAgentPrivateKeyChange(e.target.value)}
                  placeholder="Base64 Ed25519 seed"
                  autoComplete="off"
                  spellCheck={false}
                />
                <span className="field-hint">
                  Demo mode only. Do not paste production private keys.
                </span>
              </label>
            </div>
            <div className="panel__actions">
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => void handleUseAgentCredentials()}
                disabled={!agentCredentialsFilled || credentialsStatus.kind === 'loading'}
              >
                {credentialsStatus.kind === 'loading' ? 'Validating…' : 'Use agent credentials'}
              </button>
            </div>
            <StatusBox status={credentialsStatus} />
          </section>

          {/* Step 3 */}
          <section className="panel">
            <h2 className="panel__heading">
              <span className="step-badge" aria-label="Step 3">3</span>
              Create signed audit event
            </h2>
            <p>
              Build an audit event, sign the unsigned canonical payload in the browser (demo mode),
              then submit it with <code>verification_method</code>, <code>signature</code>, and{' '}
              <code>agent_id</code> from the Agent DID above.
            </p>
            <div className="form-grid">
              <label>
                Event ID
                <input
                  value={eventForm.event_id}
                  onChange={(e) => setEventForm((c) => ({ ...c, event_id: e.target.value }))}
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
                disabled={eventStatus.kind === 'loading' || !agentCredentialsReady}
                title={
                  !agentCredentialsReady
                    ? 'Click "Use agent credentials" in step 2 first'
                    : undefined
                }
              >
                {eventStatus.kind === 'loading' ? 'Signing…' : 'Create signed audit event'}
              </button>
            </div>
            <StatusBox status={eventStatus} />
          </section>

          {/* Step 4 */}
          <section className="panel">
            <h2 className="panel__heading">
              <span className="step-badge" aria-label="Step 4">4</span>
              Verify/read existing batch/proof/anchor evidence
            </h2>
            <p className="operator-note">
              <strong>Operator workflow:</strong> Operators create batches and anchors using the
              admin API or the upcoming automatic anchoring service. This public dashboard does
              not accept or store admin keys.
            </p>
            <p>
              After an operator batches and anchors events, enter the identifiers below to inspect
              public read-only evidence: batch metadata, Merkle inclusion proofs, and on-chain
              anchor records.
            </p>
            <div className="form-grid">
              <label>
                Batch ID
                <input
                  value={evidenceBatchId}
                  onChange={(e) => setEvidenceBatchId(e.target.value)}
                  placeholder="Paste batch_id from operator workflow"
                  autoComplete="off"
                  spellCheck={false}
                />
              </label>
              <label>
                Event ID
                <input
                  value={evidenceEventId}
                  onChange={(e) => setEvidenceEventId(e.target.value)}
                  placeholder="event_id for Merkle proof lookup"
                  autoComplete="off"
                  spellCheck={false}
                />
              </label>
            </div>
            <div className="panel__actions">
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => void handleLookupBatch()}
                disabled={evidenceBatchStatus.kind === 'loading'}
              >
                {evidenceBatchStatus.kind === 'loading' ? 'Loading…' : 'Lookup batch'}
              </button>
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => void handleRetrieveProof()}
                disabled={evidenceProofStatus.kind === 'loading'}
              >
                {evidenceProofStatus.kind === 'loading' ? 'Retrieving…' : 'Get & verify proof'}
              </button>
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => void handleShowAnchorResult()}
                disabled={evidenceAnchorStatus.kind === 'loading'}
              >
                {evidenceAnchorStatus.kind === 'loading' ? 'Loading…' : 'Get anchor record'}
              </button>
            </div>
            {lastProof.length > 0 && evidenceProofStatus.kind !== 'loading' && (
              <p style={{ marginTop: '0.65rem', marginBottom: 0 }}>
                Cached proof steps:{' '}
                <span className="badge badge--ok">{lastProof.length}</span>
              </p>
            )}
            <StatusBox status={evidenceBatchStatus} />
            <StatusBox status={evidenceProofStatus} />
            <StatusBox status={evidenceAnchorStatus} />
          </section>

          {/* Success banner */}
          {workflow.tx_hash && (
            <div className="success-banner" role="status">
              <span className="success-banner__icon" aria-hidden="true">✓</span>
              <div>
                <strong>Verifiable audit trail completed.</strong>
                <span> The Merkle root is anchored on-chain and independently verifiable.</span>
              </div>
              {BLOCKSCOUT_CONFIGURED && (
                <a
                  className="success-banner__link"
                  href={`${BLOCKSCOUT_TX_BASE}${workflow.tx_hash}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  View on Blockscout <ExternalLinkIcon />
                </a>
              )}
            </div>
          )}

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

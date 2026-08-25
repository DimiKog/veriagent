import { useCallback, useState } from 'react'
import {
  BLOCKSCOUT_CONFIGURED,
  BLOCKSCOUT_TX_BASE,
  getBatch,
  getBatchAnchor,
  getBatchProof,
  getOpsStatus,
  verifyMerkleProof,
} from '../api/client'
import { CryptoBoundaryNote } from '../components/ArchitectureNotes'
import { ExternalLinkIcon } from '../components/Icons'
import { HashValue } from '../components/HashValue'
import { LifecycleStepper } from '../components/LifecycleStepper'
import { StatusBox } from '../components/StatusBox'
import { useLifecyclePolling } from '../hooks/useLifecyclePolling'
import {
  errorMessage,
  formatAnchoredAt,
  lifecyclePhaseFromStatus,
  workflowPatchFromLifecycle,
} from '../lib/format'
import { downloadJsonFile } from '../lib/downloadJson'
import type {
  BatchAnchorRecord,
  BatchProofResponse,
  BatchResponse,
  EventLifecycleStatusResponse,
  MerkleProofStep,
  OpsStatusResponse,
  SectionStatus,
  WorkflowState,
} from '../types'
import { emptyWorkflowState } from '../types'

export function DashboardPage() {
  const [workflow, setWorkflow] = useState<WorkflowState>(emptyWorkflowState)
  const [evidenceBatchId, setEvidenceBatchId] = useState('')
  const [evidenceEventId, setEvidenceEventId] = useState('')
  const [lastProof, setLastProof] = useState<MerkleProofStep[]>([])
  const [lastProofResponse, setLastProofResponse] = useState<BatchProofResponse | null>(null)
  const [lastAnchorResponse, setLastAnchorResponse] = useState<BatchAnchorRecord | null>(null)
  const [evidenceBatchStatus, setEvidenceBatchStatus] = useState<SectionStatus>({
    kind: 'idle',
  })
  const [evidenceProofStatus, setEvidenceProofStatus] = useState<SectionStatus>({
    kind: 'idle',
  })
  const [evidenceAnchorStatus, setEvidenceAnchorStatus] = useState<SectionStatus>({
    kind: 'idle',
  })
  const [opsStatus, setOpsStatus] = useState<SectionStatus>({ kind: 'idle' })
  const [opsData, setOpsData] = useState<OpsStatusResponse | null>(null)

  const applyLifecycleStatus = useCallback((status: EventLifecycleStatusResponse) => {
    setWorkflow((current) => ({ ...current, ...workflowPatchFromLifecycle(status) }))
    if (status.batch_id) setEvidenceBatchId(status.batch_id)
    setEvidenceEventId(status.event_id)
  }, [])

  const {
    trackedEventId,
    lifecycleStatus,
    lifecyclePolling,
    lifecycleFetchStatus,
    startPolling,
  } = useLifecyclePolling(applyLifecycleStatus)

  const resolvedBatchId = evidenceBatchId.trim() || workflow.batch_id.trim()
  const verificationReady = Boolean(resolvedBatchId)
  const currentLifecyclePhase = lifecyclePhaseFromStatus(
    lifecycleStatus,
    Boolean(trackedEventId || workflow.event_id),
  )

  const handleRefreshLifecycle = () => {
    startPolling(evidenceEventId)
  }

  const handleLookupBatch = async () => {
    const batchId = resolvedBatchId
    if (!batchId) {
      setEvidenceBatchStatus({
        kind: 'error',
        message: 'No batch_id yet. Wait until the event is batched, or refresh lifecycle status.',
      })
      return
    }

    setEvidenceBatchStatus({ kind: 'loading', message: 'Fetching batch metadata…' })
    try {
      const data: BatchResponse = await getBatch(batchId)
      setWorkflow((current) => ({
        ...current,
        batch_id: data.batch_id,
        merkle_root: data.merkle_root,
      }))
      setEvidenceBatchId(data.batch_id)
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
    const batchId = resolvedBatchId
    const eventId = evidenceEventId.trim()
    if (!batchId || !eventId) {
      setEvidenceProofStatus({
        kind: 'error',
        message: !eventId
          ? 'Enter an event_id to retrieve a Merkle proof.'
          : 'No batch_id yet. Wait until the event is batched, or refresh lifecycle status.',
      })
      return
    }

    setEvidenceProofStatus({ kind: 'loading', message: 'Fetching Merkle proof…' })
    try {
      const data: BatchProofResponse = await getBatchProof(batchId, eventId)
      setLastProof(data.proof)
      setLastProofResponse(data)
      setWorkflow((current) => ({
        ...current,
        batch_id: data.batch_id,
        event_id: data.event_id,
        event_hash: data.event_hash,
        merkle_root: data.merkle_root,
      }))
      setEvidenceBatchId(data.batch_id)

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
    const batchId = resolvedBatchId
    if (!batchId) {
      setEvidenceAnchorStatus({
        kind: 'error',
        message: 'No batch_id yet. Wait until the event is batched, or refresh lifecycle status.',
      })
      return
    }

    setEvidenceAnchorStatus({ kind: 'loading', message: 'Fetching anchor record…' })
    try {
      const data = await getBatchAnchor(batchId)
      setLastAnchorResponse(data)
      setWorkflow((current) => ({
        ...current,
        batch_id: data.batch_id,
        merkle_root: data.merkle_root,
        tx_hash: data.tx_hash,
        chain_id: String(data.chain_id),
        block_number: String(data.block_number),
        anchored_at: formatAnchoredAt(data.anchored_at),
      }))
      setEvidenceBatchId(data.batch_id)
      setEvidenceAnchorStatus({
        kind: 'success',
        message: 'Anchor record retrieved from the backend.',
        data,
      })
    } catch (error) {
      setEvidenceAnchorStatus({ kind: 'error', message: errorMessage(error) })
    }
  }

  const handleOpsStatus = async () => {
    setOpsStatus({ kind: 'loading', message: 'Fetching ops status…' })
    try {
      const data = await getOpsStatus()
      setOpsData(data)
      setOpsStatus({
        kind: 'success',
        message: `Scheduler ${data.scheduler_running ? 'running' : 'idle'} — last status: ${data.last_status}`,
        data,
      })
    } catch (error) {
      setOpsData(null)
      setOpsStatus({ kind: 'error', message: errorMessage(error) })
    }
  }

  return (
    <div className="dashboard__layout">
      <div className="dashboard__sections">
        <div className="readonly-banner" role="note">
          <p>
            The public dashboard is read-only by design. Anyone can independently verify evidence,
            but no unauthenticated user can create or modify audit records.
          </p>
          <p>
            Platform verification (this page) uses live API status, proofs, and anchors.
            Independent offline trust uses the CLI:{' '}
            <code>veriagent verify</code> — no platform session required.
          </p>
        </div>

        <CryptoBoundaryNote />

        <section className="panel">
          <h2 className="panel__heading">Event lifecycle & verification</h2>
          <p className="panel__helper">
            Look up an event by ID. The dashboard polls{' '}
            <code>{'GET /audit/events/{event_id}/status'}</code> until the event is batched and
            anchored. No credentials are required.
          </p>

          <LifecycleStepper
            currentPhase={currentLifecyclePhase}
            polling={lifecyclePolling}
          />

          <div className="form-grid form-grid--lifecycle">
            <label>
              Event ID
              <input
                value={evidenceEventId}
                onChange={(e) => setEvidenceEventId(e.target.value)}
                placeholder="Paste an existing event_id"
                autoComplete="off"
                spellCheck={false}
              />
            </label>
            <label>
              Batch ID
              <input
                value={resolvedBatchId}
                onChange={(e) => setEvidenceBatchId(e.target.value)}
                placeholder="Auto-filled when batched, or paste a batch_id"
                autoComplete="off"
                spellCheck={false}
              />
              <span className="field-hint">
                Filled from lifecycle status when available; you can also paste a known batch_id.
              </span>
            </label>
          </div>

          {(lifecycleStatus?.anchored || workflow.tx_hash) && (
            <dl className="anchor-meta">
              <div>
                <dt>tx_hash</dt>
                <dd>
                  <HashValue value={workflow.tx_hash || lifecycleStatus?.tx_hash || ''} />
                </dd>
              </div>
              <div>
                <dt>block_number</dt>
                <dd>
                  <HashValue
                    value={
                      workflow.block_number ||
                      (lifecycleStatus?.block_number != null
                        ? String(lifecycleStatus.block_number)
                        : '')
                    }
                  />
                </dd>
              </div>
              <div>
                <dt>anchored_at</dt>
                <dd>
                  <HashValue
                    value={
                      workflow.anchored_at || formatAnchoredAt(lifecycleStatus?.anchored_at)
                    }
                  />
                </dd>
              </div>
            </dl>
          )}

          <div className="panel__actions">
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => void handleRefreshLifecycle()}
              disabled={lifecycleFetchStatus.kind === 'loading' && lifecyclePolling}
            >
              {lifecyclePolling ? 'Polling…' : 'Refresh lifecycle'}
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => void handleLookupBatch()}
              disabled={evidenceBatchStatus.kind === 'loading' || !verificationReady}
            >
              {evidenceBatchStatus.kind === 'loading' ? 'Loading…' : 'Lookup batch'}
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => void handleRetrieveProof()}
              disabled={evidenceProofStatus.kind === 'loading' || !verificationReady}
            >
              {evidenceProofStatus.kind === 'loading' ? 'Retrieving…' : 'Get & verify proof'}
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => void handleShowAnchorResult()}
              disabled={evidenceAnchorStatus.kind === 'loading' || !verificationReady}
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

          {(lastProofResponse || lastAnchorResponse) && (
            <div className="panel__actions" style={{ marginTop: '0.75rem' }}>
              {lastProofResponse && (
                <button
                  type="button"
                  className="btn"
                  onClick={() => downloadJsonFile(lastProofResponse, 'proof.json')}
                >
                  Download proof JSON
                </button>
              )}
              {lastAnchorResponse && (
                <button
                  type="button"
                  className="btn"
                  onClick={() => downloadJsonFile(lastAnchorResponse, 'anchor.json')}
                >
                  Download anchor JSON
                </button>
              )}
            </div>
          )}

          <StatusBox status={lifecycleFetchStatus} />
          <StatusBox status={evidenceBatchStatus} />
          <StatusBox status={evidenceProofStatus} />
          <StatusBox status={evidenceAnchorStatus} />
        </section>

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

        <section className="panel">
          <h2 className="panel__heading">Ops / public stats</h2>
          <p className="panel__helper">
            Optional read-only view of auto-anchor scheduler status via{' '}
            <code>GET /ops/status</code>.
          </p>
          <div className="panel__actions">
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => void handleOpsStatus()}
              disabled={opsStatus.kind === 'loading'}
            >
              {opsStatus.kind === 'loading' ? 'Loading…' : 'Load ops status'}
            </button>
          </div>
          {opsData && (
            <dl className="ops-meta">
              <div>
                <dt>scheduler_running</dt>
                <dd>{opsData.scheduler_running ? 'yes' : 'no'}</dd>
              </div>
              <div>
                <dt>auto_anchor_enabled</dt>
                <dd>{opsData.auto_anchor_enabled ? 'yes' : 'no'}</dd>
              </div>
              <div>
                <dt>last_status</dt>
                <dd>{opsData.last_status}</dd>
              </div>
              <div>
                <dt>last_batch_id</dt>
                <dd><HashValue value={opsData.last_batch_id ?? ''} /></dd>
              </div>
              <div>
                <dt>last_anchor_tx</dt>
                <dd><HashValue value={opsData.last_anchor_tx ?? ''} /></dd>
              </div>
            </dl>
          )}
          <StatusBox status={opsStatus} />
        </section>
      </div>

      <aside className="panel workflow-panel">
        <h2 className="panel__heading">Current verification state</h2>
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
            <dt>block_number</dt>
            <HashValue value={workflow.block_number} />
          </div>
          <div>
            <dt>anchored_at</dt>
            <HashValue value={workflow.anchored_at} />
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
  )
}

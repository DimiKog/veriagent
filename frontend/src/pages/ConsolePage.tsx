import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  BLOCKSCOUT_CONFIGURED,
  BLOCKSCOUT_TX_BASE,
  CLI_API_BASE_URL,
  getBatch,
  getBatchAnchor,
  getBatchProof,
  listAgentEvents,
  verifyMerkleProof,
} from '../api/client'
import { ExternalLinkIcon } from '../components/Icons'
import { HashValue } from '../components/HashValue'
import { LifecycleStepper } from '../components/LifecycleStepper'
import { StatusBox } from '../components/StatusBox'
import { CryptoBoundaryNote, DevAuthBanner } from '../components/ArchitectureNotes'
import { useLifecyclePolling } from '../hooks/useLifecyclePolling'
import {
  errorMessage,
  formatAnchoredAt,
  lifecyclePhaseFromStatus,
  workflowPatchFromLifecycle,
} from '../lib/format'
import { isUnauthorizedError } from '../lib/authErrors'
import {
  clearAgentDevAuthKey,
  readAgentDevAuthKey,
  writeAgentDevAuthKey,
} from '../lib/devAuthStorage'
import type {
  AgentAuditEventSummary,
  EventLifecycleStatusResponse,
  MerkleProofStep,
  SectionStatus,
  WorkflowState,
} from '../types'
import { emptyWorkflowState } from '../types'

function loadStoredApiKey(): string {
  return readAgentDevAuthKey()
}

export function ConsolePage() {
  const [apiKeyInput, setApiKeyInput] = useState(loadStoredApiKey)
  const [sessionKey, setSessionKey] = useState(loadStoredApiKey)
  const [sessionVerified, setSessionVerified] = useState(false)
  const [events, setEvents] = useState<AgentAuditEventSummary[]>([])
  const [listStatus, setListStatus] = useState<SectionStatus>(() =>
    loadStoredApiKey()
      ? { kind: 'loading', message: 'Loading agent events…' }
      : { kind: 'idle' },
  )
  const [workflow, setWorkflow] = useState<WorkflowState>(emptyWorkflowState)
  const [evidenceBatchId, setEvidenceBatchId] = useState('')
  const [evidenceEventId, setEvidenceEventId] = useState('')
  const [lastProof, setLastProof] = useState<MerkleProofStep[]>([])
  const [evidenceBatchStatus, setEvidenceBatchStatus] = useState<SectionStatus>({
    kind: 'idle',
  })
  const [evidenceProofStatus, setEvidenceProofStatus] = useState<SectionStatus>({
    kind: 'idle',
  })
  const [evidenceAnchorStatus, setEvidenceAnchorStatus] = useState<SectionStatus>({
    kind: 'idle',
  })

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

  const refreshEvents = useCallback(
    async (key: string) => {
      const resolvedKey = key.trim() || readAgentDevAuthKey().trim()
      if (!resolvedKey) return
      setListStatus({ kind: 'loading', message: 'Loading agent events…' })
      try {
        const data = await listAgentEvents(resolvedKey)
        setSessionVerified(true)
        setEvents(data.events)
        setListStatus({
          kind: 'success',
          message: `Loaded ${data.events.length} event(s).`,
        })
      } catch (error) {
        setEvents([])
        if (isUnauthorizedError(error)) {
          clearAgentDevAuthKey()
          setSessionKey('')
          setApiKeyInput('')
          setSessionVerified(false)
          setListStatus({
            kind: 'error',
            message:
              'Agent API key rejected by the server. Paste your agent key again to continue.',
          })
          return
        }
        setListStatus({ kind: 'error', message: errorMessage(error) })
      }
    },
    [],
  )

  useEffect(() => {
    if (!sessionKey) return

    let cancelled = false
    const key = readAgentDevAuthKey().trim() || sessionKey.trim()

    async function loadEvents() {
      try {
        const data = await listAgentEvents(key)
        if (cancelled) return
        setSessionVerified(true)
        setEvents(data.events)
        setListStatus({
          kind: 'success',
          message: `Loaded ${data.events.length} event(s).`,
        })
      } catch (error) {
        if (cancelled) return
        setEvents([])
        if (isUnauthorizedError(error)) {
          clearAgentDevAuthKey()
          setSessionKey('')
          setApiKeyInput('')
          setSessionVerified(false)
          setListStatus({
            kind: 'error',
            message:
              'Stored agent API key is invalid. Paste your agent key again to continue.',
          })
          return
        }
        setListStatus({ kind: 'error', message: errorMessage(error) })
      }
    }

    void loadEvents()
    return () => {
      cancelled = true
    }
  }, [sessionKey])

  const handleSaveSession = async (e: FormEvent) => {
    e.preventDefault()
    const key = apiKeyInput.trim()
    if (!key) {
      setListStatus({ kind: 'error', message: 'Paste an agent API key to continue.' })
      return
    }
    setListStatus({ kind: 'loading', message: 'Validating agent API key…' })
    try {
      const data = await listAgentEvents(key)
      writeAgentDevAuthKey(key)
      setSessionKey(key)
      setSessionVerified(true)
      setEvents(data.events)
      setListStatus({
        kind: 'success',
        message: `Loaded ${data.events.length} event(s).`,
      })
    } catch (error) {
      clearAgentDevAuthKey()
      setSessionKey('')
      setSessionVerified(false)
      setEvents([])
      setListStatus({
        kind: 'error',
        message: isUnauthorizedError(error)
          ? 'Agent API key rejected by the server. Check the key from register claim.'
          : errorMessage(error),
      })
    }
  }

  const handleClearSession = () => {
    clearAgentDevAuthKey()
    setSessionKey('')
    setApiKeyInput('')
    setSessionVerified(false)
    setEvents([])
    setListStatus({ kind: 'idle' })
  }

  const handleSelectEvent = (event: AgentAuditEventSummary) => {
    setEvidenceEventId(event.event_id)
    setWorkflow((current) => ({
      ...current,
      event_id: event.event_id,
      event_hash: event.event_hash,
      batch_id: '',
      merkle_root: '',
      tx_hash: '',
      chain_id: '',
      block_number: '',
      anchored_at: '',
    }))
    setEvidenceBatchId('')
    setLastProof([])
    setEvidenceBatchStatus({ kind: 'idle' })
    setEvidenceProofStatus({ kind: 'idle' })
    setEvidenceAnchorStatus({ kind: 'idle' })
    startPolling(event.event_id)
  }

  const handleLookupBatch = async () => {
    const batchId = resolvedBatchId
    if (!batchId) {
      setEvidenceBatchStatus({
        kind: 'error',
        message: 'No batch_id yet. Wait until the event is batched.',
      })
      return
    }
    setEvidenceBatchStatus({ kind: 'loading', message: 'Fetching batch metadata…' })
    try {
      const data = await getBatch(batchId)
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
        message: 'Need both event_id and batch_id to retrieve a proof.',
      })
      return
    }
    setEvidenceProofStatus({ kind: 'loading', message: 'Fetching Merkle proof…' })
    try {
      const data = await getBatchProof(batchId, eventId)
      setLastProof(data.proof)
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
        message: 'No batch_id yet. Wait until the event is batched.',
      })
      return
    }
    setEvidenceAnchorStatus({ kind: 'loading', message: 'Fetching anchor record…' })
    try {
      const data = await getBatchAnchor(batchId)
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

  const submitCliSnippet = `veriagent submit \\
  --api-base-url ${CLI_API_BASE_URL} \\
  --api-key "$VERIAGENT_API_KEY" \\
  --private-key-file ~/.veriagent/agent.key \\
  --event ./event.json`

  const submitSdkSnippet = `import os
from pathlib import Path
from veriagent import VeriAgentClient

client = VeriAgentClient(
    api_base_url="${CLI_API_BASE_URL}",
    agent_api_key=os.environ["VERIAGENT_API_KEY"],
    private_key_base64=Path.home().joinpath(".veriagent", "agent.key").read_text().strip(),
)
client.submit_event(
    event_id="event-001",
    task_id="task-001",
    model_name="demo-model",
    tool_calls=["search"],
    input_hash="sha256:…",
    output_hash="sha256:…",
    policy_version="policy-v0.1",
)`

  const validatingStoredSession =
    Boolean(sessionKey) && !sessionVerified && listStatus.kind === 'loading'

  if (validatingStoredSession) {
    return (
      <div className="page page--narrow">
        <section className="panel">
          <h2 className="panel__heading">Operator console</h2>
          <p className="panel__helper">Checking stored agent API key against the backend…</p>
          <StatusBox status={{ kind: 'loading', message: 'Validating agent credentials…' }} />
        </section>
      </div>
    )
  }

  if (!sessionKey || !sessionVerified) {
    return (
      <div className="page page--narrow">
        <CryptoBoundaryNote />
        <DevAuthBanner>
          <p>
            Temporary development mechanism: operators paste an agent API key into sessionStorage
            so the Console can call <code>GET /audit/events</code>.
          </p>
          <p>
            <strong>Intended production model:</strong> human operators authenticate with their own
            user session (SSO/OAuth). The Console then lists agents and events for that operator.
            The agent API key remains a <em>machine credential</em> used only by the SDK/CLI on the
            agent host — not a human login secret.
          </p>
          <p>
            Do not build additional product features that depend on browser-managed agent API keys.
          </p>
        </DevAuthBanner>
        <section className="panel">
          <h2 className="panel__heading">Operator console</h2>
          <p className="panel__helper">
            Development access only. Paste an agent API key to view event history. Private keys are
            never asked for or stored here — submit events via the CLI or SDK.
          </p>
          <form className="form-grid" onSubmit={handleSaveSession}>
            <label>
              Agent API Key (machine credential — temporary console access)
              <input
                type="password"
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                placeholder="va_agent_..."
                autoComplete="off"
                spellCheck={false}
              />
              <span className="field-hint">
                Stored in sessionStorage for this tab only. Cleared when the tab closes.
              </span>
            </label>
            <div className="panel__actions" style={{ gridColumn: '1 / -1' }}>
              <button type="submit" className="btn btn--primary">
                Open console
              </button>
            </div>
          </form>
          <StatusBox status={listStatus} />
        </section>
      </div>
    )
  }

  return (
    <div className="dashboard__layout">
      <div className="dashboard__sections">
        <DevAuthBanner title="Development authentication (console)">
          <p>
            Agent API key paste is temporary. Production Console should use operator user sessions;
            agent API keys stay on the machine running the SDK/CLI.
          </p>
        </DevAuthBanner>

        <section className="panel">
          <h2 className="panel__heading">
            Session
            <span className="badge badge--ok">Verified</span>
          </h2>
          <p className="panel__helper">
            Agent API key validated by the backend (<code>X-VeriAgent-API-Key</code>). No private
            keys in the browser.
          </p>
          <div className="panel__actions">
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => void refreshEvents(sessionKey)}
              disabled={listStatus.kind === 'loading'}
            >
              {listStatus.kind === 'loading' ? 'Refreshing…' : 'Refresh events'}
            </button>
            <button type="button" className="btn" onClick={handleClearSession}>
              Clear session
            </button>
          </div>
          <StatusBox status={listStatus} />
        </section>

        <section className="panel">
          <h2 className="panel__heading">Event history</h2>
          {events.length === 0 ? (
            <p className="panel__helper">No events yet for this agent.</p>
          ) : (
            <ul className="event-list">
              {events.map((event) => (
                <li key={event.event_id}>
                  <button
                    type="button"
                    className={`event-list__item${
                      evidenceEventId === event.event_id ? ' event-list__item--active' : ''
                    }`}
                    onClick={() => handleSelectEvent(event)}
                  >
                    <span className="event-list__id">
                      <HashValue value={event.event_id} />
                    </span>
                    <span className="event-list__meta">
                      {event.anchored ? (
                        <span className="badge badge--ok">Anchored</span>
                      ) : event.batched ? (
                        <span className="badge badge--pending">Batched</span>
                      ) : (
                        <span className="badge badge--pending">Submitted</span>
                      )}
                      <time dateTime={event.created_at}>{event.created_at}</time>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel">
          <h2 className="panel__heading">Lifecycle & evidence</h2>
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
                placeholder="Select an event or paste an event_id"
                autoComplete="off"
                spellCheck={false}
              />
            </label>
            <label>
              Batch ID
              <input
                value={resolvedBatchId}
                readOnly
                placeholder="Filled when the event is batched"
                autoComplete="off"
                spellCheck={false}
              />
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
              onClick={() => startPolling(evidenceEventId)}
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
          <StatusBox status={lifecycleFetchStatus} />
          <StatusBox status={evidenceBatchStatus} />
          <StatusBox status={evidenceProofStatus} />
          <StatusBox status={evidenceAnchorStatus} />

          {workflow.tx_hash && BLOCKSCOUT_CONFIGURED && (
            <a
              className="external-link"
              href={`${BLOCKSCOUT_TX_BASE}${workflow.tx_hash}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              View on Blockscout <ExternalLinkIcon />
            </a>
          )}
        </section>

        <section className="panel">
          <h2 className="panel__heading">Submit guidance</h2>
          <p className="panel__helper">
            Sign and submit audit events outside the browser. Do not paste agent private keys here.
          </p>
          <h3 className="cli-block__heading">CLI</h3>
          <pre className="cli-command">{submitCliSnippet}</pre>
          <h3 className="cli-block__heading">Python SDK</h3>
          <pre className="cli-command">{submitSdkSnippet}</pre>
        </section>
      </div>

      <aside className="panel workflow-panel">
        <h2 className="panel__heading">Selected event</h2>
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
        </dl>
      </aside>
    </div>
  )
}

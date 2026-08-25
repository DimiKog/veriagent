import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  approveRegistrationRequest,
  getOpsStatus,
  listRegistrationRequests,
  rejectRegistrationRequest,
} from '../api/client'
import { CryptoBoundaryNote, DevAuthBanner } from '../components/ArchitectureNotes'
import { HashValue } from '../components/HashValue'
import { StatusBox } from '../components/StatusBox'
import { errorMessage } from '../lib/format'
import { isUnauthorizedError } from '../lib/authErrors'
import {
  clearAdminDevAuthKey,
  readAdminDevAuthKey,
  writeAdminDevAuthKey,
} from '../lib/devAuthStorage'
import type {
  AdminRegistrationRequestSummary,
  OpsStatusResponse,
  SectionStatus,
} from '../types'

function loadStoredAdminKey(): string {
  return readAdminDevAuthKey()
}

export function AdminPage() {
  const [adminKeyInput, setAdminKeyInput] = useState(loadStoredAdminKey)
  const [sessionKey, setSessionKey] = useState(loadStoredAdminKey)
  const [sessionVerified, setSessionVerified] = useState(false)
  const [requests, setRequests] = useState<AdminRegistrationRequestSummary[]>([])
  const [queueStatus, setQueueStatus] = useState<SectionStatus>(() =>
    loadStoredAdminKey()
      ? { kind: 'loading', message: 'Loading pending registration requests…' }
      : { kind: 'idle' },
  )
  const [actionStatus, setActionStatus] = useState<SectionStatus>({ kind: 'idle' })
  const [notesById, setNotesById] = useState<Record<string, string>>({})
  const [opsStatus, setOpsStatus] = useState<SectionStatus>(() =>
    loadStoredAdminKey()
      ? { kind: 'loading', message: 'Loading ops status…' }
      : { kind: 'idle' },
  )
  const [opsData, setOpsData] = useState<OpsStatusResponse | null>(null)

  const invalidateSession = useCallback((message: string) => {
    clearAdminDevAuthKey()
    setSessionKey('')
    setAdminKeyInput('')
    setSessionVerified(false)
    setRequests([])
    setQueueStatus({ kind: 'error', message })
    setActionStatus({ kind: 'idle' })
    setOpsData(null)
    setOpsStatus({ kind: 'idle' })
  }, [])

  const refreshQueue = useCallback(
    async (key: string) => {
      const resolvedKey = key.trim() || readAdminDevAuthKey().trim()
      if (!resolvedKey) return
      setQueueStatus({ kind: 'loading', message: 'Loading pending registration requests…' })
      try {
        const data = await listRegistrationRequests(resolvedKey, 'pending')
        setSessionVerified(true)
        setRequests(data.requests)
        setQueueStatus({
          kind: 'success',
          message: `${data.requests.length} pending request(s).`,
        })
      } catch (error) {
        setRequests([])
        if (isUnauthorizedError(error)) {
          invalidateSession(
            'Admin key rejected by the server. Unlock again with your admin API key.',
          )
          return
        }
        setQueueStatus({ kind: 'error', message: errorMessage(error) })
      }
    },
    [invalidateSession],
  )

  const refreshOps = useCallback(async () => {
    setOpsStatus({ kind: 'loading', message: 'Loading ops status…' })
    try {
      const data = await getOpsStatus()
      setOpsData(data)
      setOpsStatus({
        kind: 'success',
        message: `Scheduler ${data.scheduler_running ? 'running' : 'idle'} — ${data.last_status}`,
      })
    } catch (error) {
      setOpsData(null)
      setOpsStatus({ kind: 'error', message: errorMessage(error) })
    }
  }, [])

  useEffect(() => {
    if (!sessionKey) return

    let cancelled = false
    const key = readAdminDevAuthKey().trim() || sessionKey.trim()

    async function loadQueue() {
      try {
        const data = await listRegistrationRequests(key, 'pending')
        if (cancelled) return
        setSessionVerified(true)
        setRequests(data.requests)
        setQueueStatus({
          kind: 'success',
          message: `${data.requests.length} pending request(s).`,
        })
      } catch (error) {
        if (cancelled) return
        setRequests([])
        if (isUnauthorizedError(error)) {
          invalidateSession(
            'Stored admin key is invalid or was replaced. Unlock again with your admin API key.',
          )
          return
        }
        setQueueStatus({ kind: 'error', message: errorMessage(error) })
      }
    }

    async function loadOps() {
      try {
        const data = await getOpsStatus()
        if (cancelled) return
        setOpsData(data)
        setOpsStatus({
          kind: 'success',
          message: `Scheduler ${data.scheduler_running ? 'running' : 'idle'} — ${data.last_status}`,
        })
      } catch (error) {
        if (cancelled) return
        setOpsData(null)
        setOpsStatus({ kind: 'error', message: errorMessage(error) })
      }
    }

    void loadQueue()
    void loadOps()
    return () => {
      cancelled = true
    }
  }, [sessionKey, invalidateSession])

  const handleSaveSession = async (e: FormEvent) => {
    e.preventDefault()
    const key = adminKeyInput.trim()
    if (!key) {
      setQueueStatus({ kind: 'error', message: 'Enter an admin key to continue.' })
      return
    }
    setQueueStatus({
      kind: 'loading',
      message: 'Validating admin key…',
    })
    setOpsStatus({ kind: 'loading', message: 'Loading ops status…' })
    try {
      const data = await listRegistrationRequests(key, 'pending')
      writeAdminDevAuthKey(key)
      setSessionKey(key)
      setSessionVerified(true)
      setRequests(data.requests)
      setQueueStatus({
        kind: 'success',
        message: `${data.requests.length} pending request(s).`,
      })
      try {
        const ops = await getOpsStatus()
        setOpsData(ops)
        setOpsStatus({
          kind: 'success',
          message: `Scheduler ${ops.scheduler_running ? 'running' : 'idle'} — ${ops.last_status}`,
        })
      } catch (error) {
        setOpsData(null)
        setOpsStatus({ kind: 'error', message: errorMessage(error) })
      }
    } catch (error) {
      clearAdminDevAuthKey()
      setSessionKey('')
      setSessionVerified(false)
      setRequests([])
      setOpsData(null)
      setOpsStatus({ kind: 'idle' })
      setQueueStatus({
        kind: 'error',
        message: isUnauthorizedError(error)
          ? 'Admin key rejected by the server. Check VERIAGENT_ADMIN_API_KEY in backend/.env.'
          : errorMessage(error),
      })
    }
  }

  const handleClearSession = () => {
    clearAdminDevAuthKey()
    setSessionKey('')
    setAdminKeyInput('')
    setSessionVerified(false)
    setRequests([])
    setQueueStatus({ kind: 'idle' })
    setActionStatus({ kind: 'idle' })
    setOpsData(null)
    setOpsStatus({ kind: 'idle' })
  }

  const handleApprove = async (requestId: string) => {
    setActionStatus({ kind: 'loading', message: `Approving ${requestId}…` })
    try {
      const result = await approveRegistrationRequest(
        sessionKey,
        requestId,
        notesById[requestId]?.trim() || undefined,
      )
      setActionStatus({
        kind: 'success',
        message: `Approved ${result.request_id}. Agent ${result.approved_agent_did} is active — applicant must claim credentials via CLI.`,
        data: {
          request_id: result.request_id,
          status: result.status,
          approved_agent_did: result.approved_agent_did,
          agent_status: result.agent_status,
          reviewed_at: result.reviewed_at,
          retrieval_token: result.retrieval_token,
        },
      })
      await refreshQueue(sessionKey)
    } catch (error) {
      if (isUnauthorizedError(error)) {
        invalidateSession(
          'Admin key rejected by the server. Unlock again with your admin API key.',
        )
        return
      }
      setActionStatus({ kind: 'error', message: errorMessage(error) })
    }
  }

  const handleReject = async (requestId: string) => {
    setActionStatus({ kind: 'loading', message: `Rejecting ${requestId}…` })
    try {
      const result = await rejectRegistrationRequest(
        sessionKey,
        requestId,
        notesById[requestId]?.trim() || undefined,
      )
      setActionStatus({
        kind: 'success',
        message: `Rejected ${result.request_id}.`,
        data: result,
      })
      await refreshQueue(sessionKey)
    } catch (error) {
      if (isUnauthorizedError(error)) {
        invalidateSession(
          'Admin key rejected by the server. Unlock again with your admin API key.',
        )
        return
      }
      setActionStatus({ kind: 'error', message: errorMessage(error) })
    }
  }

  const validatingStoredSession =
    Boolean(sessionKey) && !sessionVerified && queueStatus.kind === 'loading'

  if (validatingStoredSession) {
    return (
      <div className="page page--narrow">
        <section className="panel">
          <h2 className="panel__heading">Admin session</h2>
          <p className="panel__helper">Checking stored admin key against the backend…</p>
          <StatusBox status={{ kind: 'loading', message: 'Validating admin credentials…' }} />
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
            Development authentication. The admin API key is pasted into sessionStorage and sent as{' '}
            <code>X-VeriAgent-Admin-Key</code>. This is intended to be replaced by proper
            authenticated sessions (SSO/OAuth/Keycloak/etc.).
          </p>
          <p>
            Do not build additional admin product features that depend on browser-managed admin
            keys beyond this temporary unlock gate.
          </p>
        </DevAuthBanner>
        <section className="panel">
          <h2 className="panel__heading">Admin control plane</h2>
          <p className="panel__helper">
            Temporary unlock for local/dev operators. Never put the admin key in the URL.
          </p>
          <form className="form-grid" onSubmit={handleSaveSession}>
            <label>
              Admin key
              <input
                type="password"
                value={adminKeyInput}
                onChange={(e) => setAdminKeyInput(e.target.value)}
                placeholder="Admin API key"
                autoComplete="off"
                spellCheck={false}
              />
            </label>
            <div className="panel__actions" style={{ gridColumn: '1 / -1' }}>
              <button type="submit" className="btn btn--primary">
                Unlock admin
              </button>
            </div>
          </form>
          <StatusBox status={queueStatus} />
        </section>
      </div>
    )
  }

  return (
    <div className="dashboard__sections">
      <DevAuthBanner title="Development authentication (admin)">
        <p>
          Development authentication. Intended to be replaced by proper authenticated sessions
          (SSO/OAuth/Keycloak/etc.).
        </p>
      </DevAuthBanner>

      <section className="panel">
        <h2 className="panel__heading">
          Admin session
          <span className="badge badge--ok">Verified</span>
        </h2>
        <p className="panel__helper">
          Admin key validated by the backend (<code>X-VeriAgent-Admin-Key</code>).
        </p>
        <div className="panel__actions">
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void refreshQueue(sessionKey)}
            disabled={queueStatus.kind === 'loading'}
          >
            {queueStatus.kind === 'loading' ? 'Refreshing…' : 'Refresh queue'}
          </button>
          <button type="button" className="btn" onClick={handleClearSession}>
            Clear session
          </button>
        </div>
        <StatusBox status={queueStatus} />
        <StatusBox status={actionStatus} />
      </section>

      <section className="panel">
        <h2 className="panel__heading">Pending registration queue</h2>
        {requests.length === 0 ? (
          <p className="panel__helper">No pending registration requests.</p>
        ) : (
          <ul className="admin-queue">
            {requests.map((req) => (
              <li key={req.request_id} className="admin-queue__item">
                <div className="admin-queue__header">
                  <strong>{req.agent_name}</strong>
                  <span className="badge badge--pending">{req.status}</span>
                  {req.proof_submitted_at ? (
                    <span className="badge badge--ok">Proof submitted</span>
                  ) : (
                    <span className="badge badge--fail">Proof required</span>
                  )}
                </div>
                <dl className="ops-meta">
                  <div>
                    <dt>request_id</dt>
                    <dd><HashValue value={req.request_id} /></dd>
                  </div>
                  <div>
                    <dt>agent_did</dt>
                    <dd><HashValue value={req.agent_did} /></dd>
                  </div>
                  <div>
                    <dt>organization</dt>
                    <dd>{req.organization_name}</dd>
                  </div>
                  <div>
                    <dt>contact</dt>
                    <dd>{req.contact_email}</dd>
                  </div>
                  <div>
                    <dt>use_case</dt>
                    <dd>{req.use_case_summary}</dd>
                  </div>
                  <div>
                    <dt>challenge_expires_at</dt>
                    <dd>{req.challenge_expires_at}</dd>
                  </div>
                </dl>
                <label className="admin-queue__notes">
                  Review notes
                  <textarea
                    value={notesById[req.request_id] ?? ''}
                    onChange={(e) =>
                      setNotesById((current) => ({
                        ...current,
                        [req.request_id]: e.target.value,
                      }))
                    }
                    placeholder="Optional notes for approve/reject"
                  />
                </label>
                <div className="panel__actions">
                  <button
                    type="button"
                    className="btn btn--primary"
                    onClick={() => void handleApprove(req.request_id)}
                    disabled={
                      actionStatus.kind === 'loading' || !req.proof_submitted_at
                    }
                    title={
                      !req.proof_submitted_at
                        ? 'Proof must be submitted before approval'
                        : undefined
                    }
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => void handleReject(req.request_id)}
                    disabled={actionStatus.kind === 'loading'}
                  >
                    Reject
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel">
        <h2 className="panel__heading">Ops scheduler</h2>
        <p className="panel__helper">
          Public <code>GET /ops/status</code> — auto-anchor scheduler health.
        </p>
        <div className="panel__actions">
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void refreshOps()}
            disabled={opsStatus.kind === 'loading'}
          >
            {opsStatus.kind === 'loading' ? 'Loading…' : 'Refresh ops'}
          </button>
        </div>
        {opsData && (
          <dl className="ops-meta">
            <div>
              <dt>service</dt>
              <dd>{opsData.service} v{opsData.version}</dd>
            </div>
            <div>
              <dt>scheduler_running</dt>
              <dd>{opsData.scheduler_running ? 'yes' : 'no'}</dd>
            </div>
            <div>
              <dt>auto_anchor_enabled</dt>
              <dd>{opsData.auto_anchor_enabled ? 'yes' : 'no'}</dd>
            </div>
            <div>
              <dt>interval_seconds</dt>
              <dd>{opsData.interval_seconds}</dd>
            </div>
            <div>
              <dt>min_events</dt>
              <dd>{opsData.min_events}</dd>
            </div>
            <div>
              <dt>last_run_at</dt>
              <dd>{opsData.last_run_at ?? '—'}</dd>
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
            <div>
              <dt>last_error</dt>
              <dd>{opsData.last_error ?? '—'}</dd>
            </div>
          </dl>
        )}
        <StatusBox status={opsStatus} />
      </section>

      <section className="panel">
        <h2 className="panel__heading">Placeholders</h2>
        <ul className="placeholder-list">
          <li>
            <strong>Active agents list</strong> — endpoint not yet available in the public admin
            API.
          </li>
          <li>
            <strong>Revoked agents</strong> — endpoint not yet available.
          </li>
          <li>
            <strong>API key management</strong> — rotation / revoke endpoints not yet available.
          </li>
        </ul>
      </section>
    </div>
  )
}

import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  CLI_API_BASE_URL,
  createRegistrationRequest,
  getRegistrationRequestStatus,
} from '../api/client'
import { CryptoBoundaryNote } from '../components/ArchitectureNotes'
import { HashValue } from '../components/HashValue'
import { RegistrationLifecycleStepper } from '../components/RegistrationLifecycleStepper'
import { StatusBox } from '../components/StatusBox'
import { errorMessage } from '../lib/format'
import {
  phaseFromStatus,
  phaseLabel,
  shouldContinueRegistrationPoll,
} from '../lib/registrationPhase'
import type {
  CreateRegistrationRequestResponse,
  RegistrationRequestStatusResponse,
  SectionStatus,
} from '../types'

const REGISTRATION_POLL_MS = 4000

const emptyForm = {
  agent_name: '',
  agent_type: '',
  agent_did: '',
  verification_method: '',
  public_key: '',
  organization_name: '',
  contact_email: '',
  use_case_summary: '',
  description: '',
}

export function RegisterPage() {
  const [form, setForm] = useState(emptyForm)
  const [submitStatus, setSubmitStatus] = useState<SectionStatus>({ kind: 'idle' })
  const [created, setCreated] = useState<CreateRegistrationRequestResponse | null>(null)
  const [requestStatus, setRequestStatus] =
    useState<RegistrationRequestStatusResponse | null>(null)
  const [pollStatus, setPollStatus] = useState<SectionStatus>({ kind: 'idle' })
  const [justCreated, setJustCreated] = useState(false)
  const pollGenerationRef = useRef(0)

  const requestId = created?.request_id ?? requestStatus?.request_id ?? ''
  const phase = phaseFromStatus(requestStatus, justCreated && Boolean(created))
  const polling =
    Boolean(requestId) && shouldContinueRegistrationPoll(requestStatus)

  useEffect(() => {
    if (!requestId || !polling) return

    const generation = ++pollGenerationRef.current
    let cancelled = false
    let timerId: ReturnType<typeof setTimeout> | undefined

    const scheduleNext = () => {
      timerId = setTimeout(() => {
        void pollOnce()
      }, REGISTRATION_POLL_MS)
    }

    async function pollOnce() {
      if (cancelled || pollGenerationRef.current !== generation) return
      try {
        const status = await getRegistrationRequestStatus(requestId)
        if (cancelled || pollGenerationRef.current !== generation) return
        setRequestStatus(status)
        setJustCreated(false)
        setPollStatus({
          kind: 'success',
          message: `Status: ${phaseLabel(phaseFromStatus(status, false))}`,
          data: status,
        })
        if (shouldContinueRegistrationPoll(status)) {
          scheduleNext()
        }
      } catch (error) {
        if (cancelled || pollGenerationRef.current !== generation) return
        setPollStatus({
          kind: 'error',
          message: `Status poll failed — retrying. ${errorMessage(error)}`,
        })
        scheduleNext()
      }
    }

    void pollOnce()

    return () => {
      cancelled = true
      if (timerId !== undefined) clearTimeout(timerId)
    }
  }, [requestId, polling])

  const updateField = (key: keyof typeof emptyForm, value: string) => {
    setForm((current) => ({ ...current, [key]: value }))
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSubmitStatus({ kind: 'loading', message: 'Submitting registration request…' })
    try {
      const body = {
        agent_name: form.agent_name.trim(),
        agent_type: form.agent_type.trim(),
        agent_did: form.agent_did.trim(),
        verification_method: form.verification_method.trim(),
        public_key: form.public_key.trim(),
        organization_name: form.organization_name.trim(),
        contact_email: form.contact_email.trim(),
        use_case_summary: form.use_case_summary.trim(),
        ...(form.description.trim()
          ? { description: form.description.trim() }
          : {}),
      }
      const data = await createRegistrationRequest(body)
      setCreated(data)
      setJustCreated(true)
      setRequestStatus(null)
      setPollStatus({ kind: 'loading', message: 'Polling registration status…' })
      setSubmitStatus({
        kind: 'success',
        message:
          'Registration request created. Prove ownership with the CLI, then wait for approval.',
        data: {
          request_id: data.request_id,
          agent_did: data.agent_did,
          challenge_expires_at: data.challenge_expires_at,
        },
      })
    } catch (error) {
      setSubmitStatus({ kind: 'error', message: errorMessage(error) })
    }
  }

  const handleStartNew = () => {
    pollGenerationRef.current += 1
    setCreated(null)
    setRequestStatus(null)
    setJustCreated(false)
    setSubmitStatus({ kind: 'idle' })
    setPollStatus({ kind: 'idle' })
  }

  const proveCommand = requestId
    ? `veriagent register prove --request-id ${requestId} --api-base-url ${CLI_API_BASE_URL} --private-key-file ~/.veriagent/agent.key`
    : ''
  const claimCommand = requestId
    ? `veriagent register claim --request-id ${requestId} --api-base-url ${CLI_API_BASE_URL} --private-key-file ~/.veriagent/agent.key`
    : ''

  const showForm = phase === 'idle' || phase === 'expired'
  const badgeClass =
    phase === 'approved' || phase === 'credentials_claimed'
      ? 'badge--ok'
      : phase === 'rejected' || phase === 'expired'
        ? 'badge--fail'
        : 'badge--pending'

  return (
    <div className="page page--narrow">
      <CryptoBoundaryNote />

      <section className="panel">
        <h2 className="panel__heading">Agent registration</h2>
        <p className="panel__helper">
          Submit a registration request with your public identity material. The browser never
          generates keys, never asks for a private key, and never signs challenges — use the
          VeriAgent CLI on the agent host.
        </p>

        <RegistrationLifecycleStepper currentPhase={phase} polling={polling} />

        {phase !== 'idle' && (
          <div className="registration-phase" aria-live="polite">
            <span className={`badge ${badgeClass}`}>{phaseLabel(phase)}</span>
            {requestId && (
              <span className="registration-phase__id">
                request_id: <HashValue value={requestId} />
              </span>
            )}
          </div>
        )}

        {showForm && (
          <form className="form-grid" onSubmit={(e) => void handleSubmit(e)}>
            {phase === 'expired' && (
              <p className="operator-note" style={{ gridColumn: '1 / -1' }}>
                This challenge expired. Submit a new registration request below.
              </p>
            )}
            <label>
              Agent name
              <input
                required
                value={form.agent_name}
                onChange={(e) => updateField('agent_name', e.target.value)}
                autoComplete="off"
              />
            </label>
            <label>
              Agent type
              <input
                required
                value={form.agent_type}
                onChange={(e) => updateField('agent_type', e.target.value)}
                placeholder="e.g. assistant, tool-runner"
                autoComplete="off"
              />
            </label>
            <label>
              Agent DID
              <input
                required
                value={form.agent_did}
                onChange={(e) => updateField('agent_did', e.target.value)}
                placeholder="did:key:z..."
                autoComplete="off"
                spellCheck={false}
              />
            </label>
            <label>
              Verification method
              <input
                required
                value={form.verification_method}
                onChange={(e) => updateField('verification_method', e.target.value)}
                placeholder="did:key:z...#z..."
                autoComplete="off"
                spellCheck={false}
              />
            </label>
            <label>
              Public key
              <input
                required
                value={form.public_key}
                onChange={(e) => updateField('public_key', e.target.value)}
                placeholder="Base64 Ed25519 public key"
                autoComplete="off"
                spellCheck={false}
              />
            </label>
            <label>
              Organization name
              <input
                required
                value={form.organization_name}
                onChange={(e) => updateField('organization_name', e.target.value)}
                autoComplete="organization"
              />
            </label>
            <label>
              Contact email
              <input
                required
                type="email"
                value={form.contact_email}
                onChange={(e) => updateField('contact_email', e.target.value)}
                autoComplete="email"
              />
            </label>
            <label>
              Use case summary
              <textarea
                required
                value={form.use_case_summary}
                onChange={(e) => updateField('use_case_summary', e.target.value)}
                placeholder="How will this agent use VeriAgent?"
              />
            </label>
            <label>
              Description (optional)
              <textarea
                value={form.description}
                onChange={(e) => updateField('description', e.target.value)}
                placeholder="Optional agent description"
              />
            </label>
            <div className="panel__actions" style={{ gridColumn: '1 / -1' }}>
              <button
                type="submit"
                className="btn btn--primary"
                disabled={submitStatus.kind === 'loading'}
              >
                {submitStatus.kind === 'loading' ? 'Submitting…' : 'Submit registration request'}
              </button>
            </div>
          </form>
        )}

        <StatusBox status={submitStatus} />

        {created && (
          <div className="cli-block">
            <h3 className="cli-block__heading">Challenge</h3>
            <dl className="ops-meta">
              <div>
                <dt>request_id</dt>
                <dd><HashValue value={created.request_id} /></dd>
              </div>
              <div>
                <dt>challenge_expires_at</dt>
                <dd>{created.challenge_expires_at}</dd>
              </div>
              <div>
                <dt>agent_did</dt>
                <dd><HashValue value={created.agent_did} /></dd>
              </div>
            </dl>

            {(phase === 'requested' || phase === 'proof_required') && (
              <>
                <h3 className="cli-block__heading">Prove ownership (CLI)</h3>
                <p className="panel__helper">
                  Run this on a machine that holds the agent private key. The browser does not sign
                  registration challenges.
                </p>
                <pre className="cli-command">{proveCommand}</pre>
              </>
            )}

            {phase === 'pending_approval' && (
              <p className="operator-note">
                Proof verified. Waiting for admin approval (Pending approval).
              </p>
            )}

            {phase === 'approved' && requestStatus?.credentials_available && (
              <>
                <h3 className="cli-block__heading">Claim credentials (CLI)</h3>
                <p className="panel__helper">
                  Approved. Claim the one-time agent API key with the CLI. That key is a machine
                  credential for the SDK/CLI — not for pasting into the console long-term.
                </p>
                <pre className="cli-command">{claimCommand}</pre>
              </>
            )}

            {phase === 'credentials_claimed' && (
              <p className="operator-note">
                Credentials claimed
                {requestStatus?.credentials_claimed_at
                  ? ` at ${requestStatus.credentials_claimed_at}`
                  : ''}
                . Configure the agent runtime with the issued API key and continue with{' '}
                <code>veriagent submit</code>.
              </p>
            )}

            {phase === 'approved' &&
              requestStatus &&
              !requestStatus.credentials_available &&
              !requestStatus.credentials_claimed && (
                <p className="operator-note">
                  Approved, but credentials are no longer available via this flow (already claimed
                  or issued via operator relay).
                </p>
              )}

            {phase === 'rejected' && (
              <p className="operator-note">
                This registration request was rejected.
                {requestStatus?.reviewed_at
                  ? ` Reviewed at ${requestStatus.reviewed_at}.`
                  : ''}
              </p>
            )}

            {phase === 'expired' && (
              <div className="panel__actions">
                <button type="button" className="btn btn--primary" onClick={handleStartNew}>
                  Submit a new registration request
                </button>
              </div>
            )}
          </div>
        )}

        <StatusBox status={pollStatus} />
      </section>
    </div>
  )
}

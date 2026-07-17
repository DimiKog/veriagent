import type { RegistrationUiPhase } from '../lib/registrationPhase'

const STEPS: ReadonlyArray<{ phase: RegistrationUiPhase; label: string }> = [
  { phase: 'requested', label: 'Requested' },
  { phase: 'proof_required', label: 'Proof required' },
  { phase: 'proof_verified', label: 'Proof verified' },
  { phase: 'pending_approval', label: 'Pending approval' },
  { phase: 'approved', label: 'Approved' },
  { phase: 'credentials_claimed', label: 'Credentials claimed' },
]

const PHASE_ORDER: Record<Exclude<RegistrationUiPhase, 'idle' | 'rejected' | 'expired'>, number> =
  {
    requested: 0,
    proof_required: 1,
    proof_verified: 2,
    pending_approval: 3,
    approved: 4,
    credentials_claimed: 5,
  }

export function RegistrationLifecycleStepper({
  currentPhase,
  polling,
}: {
  currentPhase: RegistrationUiPhase
  polling: boolean
}) {
  if (currentPhase === 'idle') {
    return null
  }

  if (currentPhase === 'rejected' || currentPhase === 'expired') {
    return (
      <p className="operator-note" role="status">
        Registration {currentPhase}.
      </p>
    )
  }

  const currentIndex = PHASE_ORDER[currentPhase]

  return (
    <ol className="lifecycle lifecycle--registration" aria-label="Registration lifecycle">
      {STEPS.map(({ phase, label }, index) => {
        const done = currentIndex > index
        const active = currentIndex === index
        const waiting =
          active &&
          polling &&
          (phase === 'proof_required' ||
            phase === 'pending_approval' ||
            phase === 'approved')
        let stateClass = 'lifecycle__step--pending'
        if (done) stateClass = 'lifecycle__step--done'
        else if (active) stateClass = 'lifecycle__step--active'

        return (
          <li key={phase} className={`lifecycle__step ${stateClass}`}>
            <span
              className={`lifecycle__marker${waiting ? ' lifecycle__marker--spin' : ''}`}
              aria-hidden="true"
            >
              {done ? '✓' : waiting ? '↻' : index + 1}
            </span>
            <span className="lifecycle__label">{label}</span>
          </li>
        )
      })}
    </ol>
  )
}

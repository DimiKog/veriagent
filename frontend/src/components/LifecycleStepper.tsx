import type { LifecyclePhase } from '../types'

const LIFECYCLE_STEPS: ReadonlyArray<{ phase: LifecyclePhase; label: string }> = [
  { phase: 'submitted', label: 'Submitted' },
  { phase: 'batched', label: 'Batched' },
  { phase: 'anchored', label: 'Anchored' },
]

export function LifecycleStepper({
  currentPhase,
  polling,
}: {
  currentPhase: LifecyclePhase | null
  polling: boolean
}) {
  const phaseOrder: Record<LifecyclePhase, number> = {
    submitted: 0,
    batched: 1,
    anchored: 2,
  }
  const currentIndex = currentPhase === null ? -1 : phaseOrder[currentPhase]

  return (
    <ol className="lifecycle" aria-label="Event lifecycle">
      {LIFECYCLE_STEPS.map(({ phase, label }, index) => {
        const done = currentIndex > index
        const active = currentIndex === index
        const waiting = active && polling && phase !== 'anchored'
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

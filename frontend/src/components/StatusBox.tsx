import { formatJson } from '../lib/format'
import type { SectionStatus } from '../types'

export function StatusBox({ status }: { status: SectionStatus }) {
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

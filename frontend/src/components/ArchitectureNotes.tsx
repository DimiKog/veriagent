import type { ReactNode } from 'react'

/** Shared development / temporary authentication notice. */
export function DevAuthBanner({
  title = 'Development authentication',
  children,
}: {
  title?: string
  children: ReactNode
}) {
  return (
    <div className="dev-auth-banner" role="note">
      <strong>{title}</strong>
      <div className="dev-auth-banner__body">{children}</div>
    </div>
  )
}

/** Explicit production cryptographic boundary for UI surfaces. */
export function CryptoBoundaryNote() {
  return (
    <div className="crypto-boundary" role="note">
      <strong>Cryptographic boundary</strong>
      <ul>
        <li>
          <strong>SDK / CLI:</strong> DID generation, registration proof, credential claim, event
          signing
        </li>
        <li>
          <strong>Backend:</strong> verification, batching, on-chain anchoring
        </li>
        <li>
          <strong>Frontend:</strong> orchestration, monitoring, visualization, verification UI
        </li>
      </ul>
      <p>
        The browser must never become the custodian of the agent identity. Private keys are never
        generated, requested, or used for signing in production UI workflows.
      </p>
    </div>
  )
}

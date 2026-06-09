/**
 * RFC 8785 / JCS canonicalization for browser-side audit event signing.
 *
 * The Python backend (`jcs` package in `backend/app/hashing.py`) remains the
 * source of truth for verification and Merkle commitments.
 */
import canonicalize from 'canonicalize'

import type { AuditEvent } from '../types'

export class CanonicalizeError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'CanonicalizeError'
  }
}

/** Build the unsigned JSON object shape expected by the backend hasher. */
export function auditEventToUnsignedObject(event: AuditEvent): Record<string, unknown> {
  return {
    event_id: event.event_id,
    agent_id: event.agent_id,
    task_id: event.task_id,
    model_name: event.model_name,
    tool_calls: event.tool_calls,
    input_hash: event.input_hash,
    output_hash: event.output_hash,
    policy_version: event.policy_version,
    timestamp: event.timestamp,
    metadata: event.metadata ?? null,
  }
}

export function canonicalizeAuditEvent(unsignedEvent: AuditEvent): Uint8Array {
  const json = canonicalize(auditEventToUnsignedObject(unsignedEvent))
  if (json === undefined) {
    throw new CanonicalizeError('Event payload is not JSON-serializable.')
  }
  return new TextEncoder().encode(json)
}

import type { AuditEvent, SignedAuditEvent } from '../types'
import { canonicalizeAuditEvent } from './canonicalize'
import { DidKeyError, parseEd25519PrivateKeyBase64 } from './didKey'
import { ed } from './nobleEd25519'

function bytesToBase64(bytes: Uint8Array): string {
  let binary = ''
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}

export async function signAuditEvent(
  event: AuditEvent,
  privateKeyBase64: string,
  verificationMethod: string,
): Promise<SignedAuditEvent> {
  let privateKeyBytes: Uint8Array
  try {
    privateKeyBytes = parseEd25519PrivateKeyBase64(privateKeyBase64)
  } catch (error) {
    if (error instanceof DidKeyError) {
      throw error
    }
    throw new DidKeyError('Invalid private key: must be valid base64.')
  }

  const canonicalBytes = canonicalizeAuditEvent(event)
  const signatureBytes = await ed.signAsync(canonicalBytes, privateKeyBytes)

  return {
    ...event,
    verification_method: verificationMethod,
    signature: bytesToBase64(signatureBytes),
  }
}

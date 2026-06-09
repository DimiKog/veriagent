import {
  DidKeyError,
  ed25519PublicKeyToDidKey,
  parseEd25519PrivateKeyBase64,
  verificationMethodForDidKey,
} from './didKey'
import { ed } from './nobleEd25519'

export interface ValidatedAgentCredentials {
  verificationMethod: string
}

export async function validateAgentCredentials(
  agentDid: string,
  privateKeyBase64: string,
): Promise<ValidatedAgentCredentials> {
  const trimmedDid = agentDid.trim()
  if (!trimmedDid) {
    throw new DidKeyError('Agent DID is required.')
  }

  let privateKeyBytes: Uint8Array
  try {
    privateKeyBytes = parseEd25519PrivateKeyBase64(privateKeyBase64)
  } catch (error) {
    if (error instanceof DidKeyError) {
      throw error
    }
    throw new DidKeyError('Invalid private key: must be valid base64.')
  }

  let publicKeyBytes: Uint8Array
  try {
    publicKeyBytes = await ed.getPublicKeyAsync(privateKeyBytes)
  } catch {
    throw new DidKeyError('Invalid private key: could not derive Ed25519 public key.')
  }

  const derivedDid = ed25519PublicKeyToDidKey(publicKeyBytes)
  if (derivedDid !== trimmedDid) {
    throw new DidKeyError(
      `Derived DID does not match Agent DID. The private key corresponds to ${derivedDid}.`,
    )
  }

  return {
    verificationMethod: verificationMethodForDidKey(trimmedDid),
  }
}

import bs58 from 'bs58'

const ED25519_MULTICODEC_PREFIX = new Uint8Array([0xed, 0x01])
const ED25519_PUBLIC_KEY_LENGTH = 32
const ED25519_PRIVATE_KEY_LENGTH = 32
const DID_KEY_PREFIX = 'did:key:'
const ED25519_DID_KEY_PREFIX = 'did:key:z'

export class DidKeyError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'DidKeyError'
  }
}

function base64ToBytes(value: string): Uint8Array {
  const trimmed = value.trim()
  let binary: string
  try {
    binary = atob(trimmed)
  } catch {
    throw new DidKeyError('Invalid private key: must be valid base64.')
  }

  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes
}

export function parseEd25519PrivateKeyBase64(value: string): Uint8Array {
  const bytes = base64ToBytes(value)
  if (bytes.length !== ED25519_PRIVATE_KEY_LENGTH) {
    throw new DidKeyError(
      `Invalid private key: expected ${ED25519_PRIVATE_KEY_LENGTH} bytes after base64 decode.`,
    )
  }
  return bytes
}

export function ed25519PublicKeyToDidKey(publicKeyBytes: Uint8Array): string {
  if (publicKeyBytes.length !== ED25519_PUBLIC_KEY_LENGTH) {
    throw new DidKeyError('Invalid Ed25519 public key length.')
  }

  const prefixed = new Uint8Array(ED25519_MULTICODEC_PREFIX.length + publicKeyBytes.length)
  prefixed.set(ED25519_MULTICODEC_PREFIX)
  prefixed.set(publicKeyBytes, ED25519_MULTICODEC_PREFIX.length)

  const multibaseValue = `z${bs58.encode(prefixed)}`
  return `${DID_KEY_PREFIX}${multibaseValue}`
}

export function verificationMethodForDidKey(did: string): string {
  if (!did.startsWith(DID_KEY_PREFIX)) {
    throw new DidKeyError('Agent DID must start with did:key:')
  }

  const multibaseValue = did.slice(DID_KEY_PREFIX.length)
  return `${did}#${multibaseValue}`
}

export function didKeyToEd25519PublicKeyBytes(did: string): Uint8Array {
  if (!did.startsWith(ED25519_DID_KEY_PREFIX)) {
    throw new DidKeyError('Agent DID must be a valid Ed25519 did:key (did:key:z…).')
  }

  const multibaseValue = did.slice(DID_KEY_PREFIX.length)
  if (!multibaseValue.startsWith('z')) {
    throw new DidKeyError('Agent DID must be a valid Ed25519 did:key (did:key:z…).')
  }

  let prefixed: Uint8Array
  try {
    prefixed = bs58.decode(multibaseValue.slice(1))
  } catch {
    throw new DidKeyError('Invalid did:key multibase encoding.')
  }

  if (prefixed.length < ED25519_MULTICODEC_PREFIX.length) {
    throw new DidKeyError('Invalid Ed25519 multicodec prefix.')
  }

  const prefix = prefixed.subarray(0, ED25519_MULTICODEC_PREFIX.length)
  if (!prefix.every((byte, index) => byte === ED25519_MULTICODEC_PREFIX[index])) {
    throw new DidKeyError('Invalid Ed25519 multicodec prefix.')
  }

  const raw = prefixed.subarray(ED25519_MULTICODEC_PREFIX.length)
  if (raw.length !== ED25519_PUBLIC_KEY_LENGTH) {
    throw new DidKeyError('Invalid Ed25519 public key length.')
  }

  return raw
}

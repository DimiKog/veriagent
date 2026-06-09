import * as ed from '@noble/ed25519'
import { sha512 } from '@noble/hashes/sha2.js'

ed.hashes.sha512 = sha512
ed.hashes.sha512Async = (message: Uint8Array) => Promise.resolve(sha512(message))

export { ed }

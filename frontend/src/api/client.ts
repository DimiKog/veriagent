import type {
  AnchorBatchResponse,
  BatchAnchorRecord,
  BatchProofResponse,
  BatchResponse,
  HealthResponse,
  MerkleProofStep,
  MerkleVerifyResponse,
  SignedAuditEvent,
  StoreEventResponse,
} from '../types'

const PRODUCTION_API_BASE_URL = 'https://veriagent.dimikog.org'

/** Dev server proxies `/veriagent-api` → production API (see vite.config.ts). */
const DEV_API_BASE_URL = '/veriagent-api'

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? DEV_API_BASE_URL : PRODUCTION_API_BASE_URL)

/** Swagger UI — FastAPI serves `/docs` at the API host root, not under `/api/`. */
export const API_DOCS_URL = import.meta.env.DEV
  ? 'http://127.0.0.1:8000/docs'
  : `${PRODUCTION_API_BASE_URL}/docs`

export const BLOCKSCOUT_TX_BASE = 'https://blockexplorer.dimikog.org/tx/'

/** False while BLOCKSCOUT_TX_BASE is still a placeholder — hides the link in the UI. */
export const BLOCKSCOUT_CONFIGURED = !BLOCKSCOUT_TX_BASE.includes('example')

export class ApiError extends Error {
  status: number
  detail: string

  constructor(message: string, status: number, detail = '') {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }

  get displayMessage(): string {
    if (this.detail) {
      return `${this.message}: ${this.detail}`
    }
    return this.message
  }
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()
    if (
      body &&
      typeof body === 'object' &&
      'detail' in body &&
      body.detail !== undefined
    ) {
      const { detail } = body as { detail: unknown }
      if (typeof detail === 'string') {
        return detail
      }
      return JSON.stringify(detail)
    }
  } catch {
    // Response body is not JSON.
  }

  try {
    const text = await response.text()
    if (text) {
      return text
    }
  } catch {
    // Ignore read failures.
  }

  return response.statusText || 'Unknown error'
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (init?.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
    })
  } catch {
    throw new ApiError(
      'Request blocked — could not reach the VeriAgent API. If you are using the GitHub Pages dashboard, ensure the backend has CORS enabled for https://dimikog.github.io.',
      0,
    )
  }

  if (response.type === 'opaque') {
    throw new ApiError(
      'Request blocked by the browser (CORS). The backend must allow https://dimikog.github.io.',
      0,
    )
  }

  if (!response.ok) {
    const detail = await parseErrorDetail(response)
    throw new ApiError(
      `Request failed (${response.status})`,
      response.status,
      detail,
    )
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health')
}

export function storeAuditEvent(
  event: SignedAuditEvent,
  agentApiKey: string,
): Promise<StoreEventResponse> {
  return request<StoreEventResponse>('/audit/events', {
    method: 'POST',
    headers: {
      'X-VeriAgent-API-Key': agentApiKey,
    },
    body: JSON.stringify(event),
  })
}

/** User-facing message for POST /audit/events auth and signature failures. */
export function formatStoreEventError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return 'Invalid or missing agent API key. Register an agent via the admin API and paste the issued key here.'
    }
    if (error.status === 403) {
      if (error.detail === 'Invalid event signature') {
        return 'Invalid event signature. The signed canonical payload did not verify against the registered agent key. Check Agent DID, private key, and event fields.'
      }
      if (error.detail === 'verification_method does not match registered agent') {
        return 'verification_method does not match the registered agent. Re-run "Use agent credentials" with the correct Agent DID and private key.'
      }
      if (error.detail === 'event.agent_id does not match authenticated agent') {
        return 'event.agent_id does not match the authenticated agent. Use the Agent DID that matches this API key.'
      }
      return 'Request forbidden. Check that Agent DID, API key, private key, and verification_method match the registered agent.'
    }
    return error.displayMessage
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'An unexpected error occurred'
}

export function createBatch(): Promise<BatchResponse> {
  return request<BatchResponse>('/audit/batches', {
    method: 'POST',
  })
}

export function getBatchProof(
  batchId: string,
  eventId: string,
): Promise<BatchProofResponse> {
  return request<BatchProofResponse>(
    `/audit/batches/${encodeURIComponent(batchId)}/proof/${encodeURIComponent(eventId)}`,
  )
}

export function verifyMerkleProof(payload: {
  event_hash: string
  merkle_root: string
  proof: MerkleProofStep[]
}): Promise<MerkleVerifyResponse> {
  return request<MerkleVerifyResponse>('/audit/merkle/verify', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function anchorBatch(batchId: string): Promise<AnchorBatchResponse> {
  return request<AnchorBatchResponse>(
    `/audit/batches/${encodeURIComponent(batchId)}/anchor`,
    { method: 'POST' },
  )
}

export function getBatchAnchor(batchId: string): Promise<BatchAnchorRecord> {
  return request<BatchAnchorRecord>(
    `/audit/batches/${encodeURIComponent(batchId)}/anchor`,
  )
}

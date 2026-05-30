import type {
  AnchorBatchResponse,
  AuditEvent,
  BatchAnchorRecord,
  BatchProofResponse,
  BatchResponse,
  HealthResponse,
  MerkleProofStep,
  MerkleVerifyResponse,
  StoreEventResponse,
} from '../types'

const PRODUCTION_API_BASE_URL = 'https://veriagent.dimikog.org'

/** Dev server proxies `/veriagent-api` → production API (see vite.config.ts). */
const DEV_API_BASE_URL = '/veriagent-api'

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? DEV_API_BASE_URL : PRODUCTION_API_BASE_URL)

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

export function storeAuditEvent(event: AuditEvent): Promise<StoreEventResponse> {
  return request<StoreEventResponse>('/audit/events', {
    method: 'POST',
    body: JSON.stringify(event),
  })
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

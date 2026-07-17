import type {
  ApproveRegistrationRequestResponse,
  AdminRegistrationRequestListResponse,
  AgentAuditEventListResponse,
  BatchAnchorRecord,
  BatchProofResponse,
  BatchResponse,
  CreateRegistrationRequest,
  CreateRegistrationRequestResponse,
  EventLifecycleStatusResponse,
  MerkleProofStep,
  MerkleVerifyResponse,
  OpsStatusResponse,
  RegistrationRequestStatusResponse,
  RejectRegistrationRequestResponse,
} from '../types'

const PRODUCTION_API_BASE_URL = 'https://veriagent.dimikog.org'

/** Local FastAPI default for `npm run dev` (override with VITE_API_BASE_URL). */
const LOCAL_API_BASE_URL = 'http://127.0.0.1:8000'

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? LOCAL_API_BASE_URL : PRODUCTION_API_BASE_URL)

/**
 * Absolute API base for CLI snippets shown in the UI.
 * Relative proxy paths are not useful outside the browser, so fall back to
 * the local API in dev and production host otherwise.
 */
export const CLI_API_BASE_URL = API_BASE_URL.startsWith('http')
  ? API_BASE_URL
  : import.meta.env.DEV
    ? LOCAL_API_BASE_URL
    : PRODUCTION_API_BASE_URL

/** Swagger UI — FastAPI serves `/docs` at the API host root, not under `/api/`. */
export const API_DOCS_URL = import.meta.env.DEV
  ? 'http://127.0.0.1:8000/docs'
  : `${PRODUCTION_API_BASE_URL}/docs`

export const BLOCKSCOUT_TX_BASE = 'https://blockexplorer.dimikog.org/tx/'

/** False while BLOCKSCOUT_TX_BASE is still a placeholder — hides the link in the UI. */
export const BLOCKSCOUT_CONFIGURED = !BLOCKSCOUT_TX_BASE.includes('example')

export const CONTRACT_ADDRESS = '0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A'
export const CONTRACT_EXPLORER_URL = `https://blockexplorer.dimikog.org/address/${CONTRACT_ADDRESS}`

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

export function getOpsStatus(): Promise<OpsStatusResponse> {
  return request<OpsStatusResponse>('/ops/status')
}

export function listAgentEvents(
  agentApiKey: string,
  limit = 50,
  offset = 0,
): Promise<AgentAuditEventListResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  })
  return request<AgentAuditEventListResponse>(`/audit/events?${params}`, {
    headers: {
      'X-VeriAgent-API-Key': agentApiKey,
    },
  })
}

export function getEventLifecycleStatus(
  eventId: string,
): Promise<EventLifecycleStatusResponse> {
  return request<EventLifecycleStatusResponse>(
    `/audit/events/${encodeURIComponent(eventId)}/status`,
  )
}

export function getBatch(batchId: string): Promise<BatchResponse> {
  return request<BatchResponse>(
    `/audit/batches/${encodeURIComponent(batchId)}`,
  )
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

export function getBatchAnchor(batchId: string): Promise<BatchAnchorRecord> {
  return request<BatchAnchorRecord>(
    `/audit/batches/${encodeURIComponent(batchId)}/anchor`,
  )
}

/* ── Registration ─────────────────────────────────────── */

export function createRegistrationRequest(
  body: CreateRegistrationRequest,
): Promise<CreateRegistrationRequestResponse> {
  return request<CreateRegistrationRequestResponse>('/registration/requests', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function getRegistrationRequestStatus(
  requestId: string,
): Promise<RegistrationRequestStatusResponse> {
  return request<RegistrationRequestStatusResponse>(
    `/registration/requests/${encodeURIComponent(requestId)}`,
  )
}

export function listRegistrationRequests(
  adminKey: string,
  status?: string,
): Promise<AdminRegistrationRequestListResponse> {
  const params = status ? `?status=${encodeURIComponent(status)}` : ''
  return request<AdminRegistrationRequestListResponse>(
    `/registration/requests${params}`,
    {
      headers: {
        'X-VeriAgent-Admin-Key': adminKey,
      },
    },
  )
}

export function approveRegistrationRequest(
  adminKey: string,
  requestId: string,
  notes?: string,
): Promise<ApproveRegistrationRequestResponse> {
  return request<ApproveRegistrationRequestResponse>(
    `/registration/requests/${encodeURIComponent(requestId)}/approve`,
    {
      method: 'POST',
      headers: {
        'X-VeriAgent-Admin-Key': adminKey,
      },
      body: JSON.stringify({ review_notes: notes ?? null }),
    },
  )
}

export function rejectRegistrationRequest(
  adminKey: string,
  requestId: string,
  notes?: string,
): Promise<RejectRegistrationRequestResponse> {
  return request<RejectRegistrationRequestResponse>(
    `/registration/requests/${encodeURIComponent(requestId)}/reject`,
    {
      method: 'POST',
      headers: {
        'X-VeriAgent-Admin-Key': adminKey,
      },
      body: JSON.stringify({ review_notes: notes ?? null }),
    },
  )
}

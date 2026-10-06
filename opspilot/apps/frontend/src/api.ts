export const PRIORITIES = ['low', 'normal', 'high'] as const
export type Priority = (typeof PRIORITIES)[number]

export type WorkflowStatus =
  | 'RECEIVED'
  | 'VALIDATED'
  | 'QUEUED'
  | 'PROCESSING'
  | 'AWAITING_REVIEW'
  | 'COMPLETED'
  | 'FAILED'
  | 'DEAD_LETTERED'

/** States in which nothing will change without a human acting. */
export const SETTLED: readonly WorkflowStatus[] = [
  'AWAITING_REVIEW',
  'COMPLETED',
  'FAILED',
  'DEAD_LETTERED',
]

export interface OperationalRequestCreate {
  subject: string
  body: string
  requester: string
  priority: Priority
}

export interface Recommendation {
  summary: string
  requested_action: string
  missing_information: string | null
  recommended_next_step: string
  confidence_category: 'high' | 'medium' | 'low' | 'insufficient_evidence'
  citations: string[]
  limitation_disclaimer: string
}

export interface WorkflowResult {
  recommendation?: Recommendation
  insufficient_evidence?: boolean
  error?: string
}

export interface RequestDetail {
  request_id: string
  correlation_id: string
  status: WorkflowStatus
  request: OperationalRequestCreate
  result: WorkflowResult | null
  error_code: string | null
  retry_count: number
  created_at: string
  updated_at: string
  disclaimer: string
}

export interface RequestAccepted {
  request_id: string
  correlation_id: string
  status: WorkflowStatus
  created_at: string
}

const API_ROOT: string = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'
const API_BASE = `${API_ROOT}/api/v1`

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, init)
  } catch {
    throw new ApiError('Cannot reach the API. Is it running?', 0)
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body: { detail?: unknown } = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = 'Please check the form fields and try again.'
    } catch {
      /* non-JSON error body: keep the generic message */
    }
    throw new ApiError(detail, res.status)
  }
  return (await res.json()) as T
}

export const api = {
  submitRequest: (data: OperationalRequestCreate) =>
    request<RequestAccepted>('/requests', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        // Makes a double-click or network retry safe: the server returns the original request.
        'Idempotency-Key': crypto.randomUUID(),
      },
      body: JSON.stringify(data),
    }),

  getRequest: (requestId: string) => request<RequestDetail>(`/requests/${requestId}`),

  approveRequest: (requestId: string) =>
    request<{ request_id: string; status: WorkflowStatus }>(`/requests/${requestId}/approve`, {
      method: 'POST',
    }),
}

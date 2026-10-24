const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export interface ApiErrorBody {
  code: string
  message: string
  retryable: boolean
  correlation_id: string
}

export class ApiError extends Error {
  readonly status: number
  readonly body: ApiErrorBody

  constructor(status: number, body: ApiErrorBody) {
    super(body.message)
    this.status = status
    this.body = body
  }
}

let tokenSource: (() => Promise<string | undefined>) | undefined

export function setTokenSource(source: () => Promise<string | undefined>) {
  tokenSource = source
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (tokenSource) {
    try {
      headers.set('Authorization', `Bearer ${await tokenSource()}`)
    } catch {
      throw new ApiError(401, {
        code: 'AUTH_REQUIRED',
        message: 'Your session is invalid or has expired. Sign in again.',
        retryable: false,
        correlation_id: '-',
      })
    }
  }
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  } catch {
    throw new ApiError(0, {
      code: 'NETWORK_ERROR',
      message: 'The server could not be reached.',
      retryable: true,
      correlation_id: '-',
    })
  }
  if (response.ok) return (await response.json()) as T

  const data = await response.json().catch(() => null)
  throw new ApiError(
    response.status,
    data?.error ?? {
      code: `HTTP_${response.status}`,
      message: 'Unexpected server response.',
      retryable: false,
      correlation_id: response.headers.get('X-Correlation-ID') ?? '-',
    },
  )
}

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

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, init)
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

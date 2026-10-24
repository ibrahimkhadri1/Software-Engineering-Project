import { useEffect, useState } from 'react'
import { ApiError, apiFetch } from './api/client'

export default function App() {
  const [status, setStatus] = useState('Checking the server...')

  useEffect(() => {
    apiFetch<{ status: string }>('/healthz')
      .then((r) => setStatus(`Server: ${r.status}`))
      .catch((e: ApiError) => setStatus(`Server unavailable: ${e.message}`))
  }, [])

  return (
    <main>
      <h1>Canvas Autograder</h1>
      <p>{status}</p>
    </main>
  )
}

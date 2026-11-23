import { useEffect, useState, type ReactNode } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { ApiError, apiFetch, setTokenSource } from './api/client'

export default function App() {
  const { isLoading, isAuthenticated, error, loginWithRedirect } = useAuth0()

  if (isLoading) return <Screen>Loading...</Screen>
  if (!isAuthenticated) {
    return (
      <Screen>
        <p>Review AI-suggested scores and feedback for Canvas submissions, then publish the grades you approve.</p>
        {error && <p role="alert">{error.message}</p>}
        <button onClick={() => loginWithRedirect()}>Log in</button>
      </Screen>
    )
  }
  return <GraderGate />
}

function GraderGate() {
  const { user, getAccessTokenSilently, loginWithRedirect, logout } = useAuth0()
  const [me, setMe] = useState<'checking' | 'ok' | Error>('checking')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    setTokenSource(getAccessTokenSilently)
    apiFetch('/api/me')
      .then(() => setMe('ok'))
      .catch((e: Error) => setMe(e))
  }, [getAccessTokenSilently, attempt])

  const logoutButton = (
    <button onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}>Log out</button>
  )

  if (me === 'checking') return <Screen>Checking your access...</Screen>
  if (me !== 'ok') {
    return (
      <Screen>
        <p role="alert">{me.message}</p>
        {me instanceof ApiError && me.status === 401 ? (
          <button onClick={() => loginWithRedirect()}>Sign in again</button>
        ) : (
          logoutButton
        )}
        {me instanceof ApiError && me.body.retryable && (
          <button
            onClick={() => {
              setMe('checking')
              setAttempt((n) => n + 1)
            }}
          >
            Try again
          </button>
        )}
      </Screen>
    )
  }
  return (
    <Screen>
      <p>Signed in as {user?.email ?? user?.name}.</p>
      {logoutButton}
    </Screen>
  )
}

function Screen({ children }: { children: ReactNode }) {
  return (
    <main>
      <h1>Canvas Autograder</h1>
      {children}
    </main>
  )
}

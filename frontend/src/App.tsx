import { useEffect, useState, type ReactNode } from 'react'
import { Auth0Provider, useAuth0 } from '@auth0/auth0-react'
import { Navigate, Route, Routes, useNavigate } from 'react-router'
import { ApiError, apiFetch, setTokenSource } from './api/client'
import Dashboard from './screens/Dashboard'
import Review from './screens/Review'
import RubricSetup from './screens/RubricSetup'

// redirect_uri is the site root, so the page to come back to travels in appState.
const returnHere = () => ({ appState: { returnTo: window.location.pathname } })

export default function App() {
  const navigate = useNavigate()
  return (
    <Auth0Provider
      domain={import.meta.env.VITE_AUTH0_DOMAIN}
      clientId={import.meta.env.VITE_AUTH0_CLIENT_ID}
      authorizationParams={{
        redirect_uri: window.location.origin,
        audience: import.meta.env.VITE_AUTH0_AUDIENCE,
      }}
      // In-memory tokens are lost on reload where the browser blocks Auth0's third-party cookie.
      cacheLocation="localstorage"
      onRedirectCallback={(appState) => navigate(appState?.returnTo ?? '/', { replace: true })}
    >
      <SignInGate />
    </Auth0Provider>
  )
}

function SignInGate() {
  const { isLoading, isAuthenticated, error, loginWithRedirect } = useAuth0()

  if (isLoading) return <Screen>Loading...</Screen>
  if (!isAuthenticated) {
    return (
      <Screen>
        <p>Review AI-suggested scores and feedback for Canvas submissions, then publish the grades you approve.</p>
        {error && <p role="alert">{error.message}</p>}
        <button onClick={() => loginWithRedirect(returnHere())}>Log in</button>
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
          <button onClick={() => loginWithRedirect(returnHere())}>Sign in again</button>
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
      <p>
        Signed in as {user?.email ?? user?.name}. {logoutButton}
      </p>
      <Routes>
        <Route path="/" element={<RubricSetup />} />
        <Route path="/batches/:batchId" element={<Dashboard />} />
        <Route path="/results/:resultId" element={<Review />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
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

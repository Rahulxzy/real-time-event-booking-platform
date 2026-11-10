
import { useCallback, useEffect, useState } from 'react'
import './App.css'

const API_BASE = '/api'
const TOKEN_KEY = 'event_booking_access_token'

type User = {
  id: number
  email: string
  is_active: boolean
  created_at: string
}

type Event = {
  id: number
  venue_id: number
  title: string
  description: string | null
  starts_at: string
  ends_at: string
  price: string
  capacity: number
}

type Venue = {
  id: number
  name: string
  address: string
  city: string
}

type Reservation = {
  id: number
  event_id: number
  user_id: number
  status: string
  expires_at: string
  created_at: string
  confirmed_at: string | null
  total_amount: string
  seats: {
    event_seat_id: number
    row_label: string
    seat_number: number
    price: string
  }[]
}

type AuthResponse = {
  access_token: string
  token_type: string
}

type View = 'events' | 'bookings'
type AuthMode = 'login' | 'register'

async function api<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const headers = new Headers(options.headers)

  if (options.body) {
    headers.set('Content-Type', 'application/json')
  }

  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  })

  if (!response.ok) {
    const data = await response.json().catch(() => null)
    const detail = data?.detail

    let message = `Request failed (${response.status})`

    if (typeof detail === 'string') {
      message = detail
    } else if (Array.isArray(detail)) {
      message = detail.map((item) => item.msg).join(', ')
    }

    throw new Error(message)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function formatPrice(value: string | number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(Number(value))
}

function App() {
  const [token, setToken] = useState<string | null>(
    () => sessionStorage.getItem(TOKEN_KEY),
  )
  const [user, setUser] = useState<User | null>(null)
  const [events, setEvents] = useState<Event[]>([])
  const [venues, setVenues] = useState<Venue[]>([])
  const [reservations, setReservations] = useState<Reservation[]>([])
  const [view, setView] = useState<View>('events')
  const [authMode, setAuthMode] = useState<AuthMode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [selectedEvent, setSelectedEvent] = useState<Event | null>(null)
  const [loading, setLoading] = useState(true)
  const [authLoading, setAuthLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const loadPublicData = useCallback(async () => {
    const [eventData, venueData] = await Promise.all([
      api<Event[]>('/events?limit=100'),
      api<Venue[]>('/venues?limit=100'),
    ])

    setEvents(eventData)
    setVenues(venueData)
  }, [])

  const loadBookings = useCallback(async (accessToken: string) => {
    const data = await api<Reservation[]>(
      '/reservations/me',
      {},
      accessToken,
    )
    setReservations(data)
  }, [])

  const logout = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setUser(null)
    setReservations([])
    setSelectedEvent(null)
    setView('events')
    setNotice('You have been signed out.')
    setError('')
  }, [])

  useEffect(() => {
    let active = true

    async function initialize() {
      setLoading(true)

      try {
        await loadPublicData()

        if (token) {
          try {
            const currentUser = await api<User>('/auth/me', {}, token)

            if (!active) return

            setUser(currentUser)
            await loadBookings(token)
          } catch {
            if (active) logout()
          }
        }
      } catch (err) {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : 'Could not connect to the backend.',
          )
        }
      } finally {
        if (active) setLoading(false)
      }
    }

    void initialize()

    return () => {
      active = false
    }
  }, [token, loadPublicData, loadBookings, logout])

  async function handleAuth(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setNotice('')
    setAuthLoading(true)

    try {
      if (authMode === 'register') {
        await api<User>('/auth/register', {
          method: 'POST',
          body: JSON.stringify({ email, password }),
        })
      }

      const result = await api<AuthResponse>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      })

      sessionStorage.setItem(TOKEN_KEY, result.access_token)
      setToken(result.access_token)
      setPassword('')
      setNotice(
        authMode === 'register'
          ? 'Account created successfully.'
          : 'Welcome back.',
      )
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Authentication failed.',
      )
    } finally {
      setAuthLoading(false)
    }
  }

  async function handleCancel(reservationId: number) {
    if (!token) return

    const confirmed = window.confirm(
      'Are you sure you want to cancel this reservation?',
    )

    if (!confirmed) return

    setError('')
    setNotice('')

    try {
      await api<Reservation>(
        `/reservations/${reservationId}/cancel`,
        { method: 'POST' },
        token,
      )

      await loadBookings(token)
      setNotice('Reservation cancelled successfully.')
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Could not cancel reservation.',
      )
    }
  }

  function getVenue(venueId: number) {
    return venues.find((venue) => venue.id === venueId)
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a
          className="brand"
          href="#home"
          onClick={() => {
            setView('events')
            setSelectedEvent(null)
          }}
        >
          <span className="brand-mark">E</span>
          <span>Event<span className="brand-light">ly</span></span>
        </a>

        <nav className="navigation">
          <button
            className={view === 'events' ? 'nav-link active' : 'nav-link'}
            onClick={() => {
              setView('events')
              setSelectedEvent(null)
            }}
          >
            Explore events
          </button>

          {user && (
            <button
              className={view === 'bookings' ? 'nav-link active' : 'nav-link'}
              onClick={() => {
                setView('bookings')
                setSelectedEvent(null)
                setError('')
              }}
            >
              My bookings
            </button>
          )}
        </nav>

        <div className="account-area">
          {user ? (
            <>
              <span className="user-email">{user.email}</span>
              <button className="button button-outline button-small" onClick={logout}>
                Sign out
              </button>
            </>
          ) : (
            <button
              className="button button-primary button-small"
              onClick={() => {
                setAuthMode('login')
                document.getElementById('auth-panel')?.scrollIntoView({
                  behavior: 'smooth',
                })
              }}
            >
              Sign in
            </button>
          )}
        </div>
      </header>

      <main>
        <section className="hero-section">
          <div className="hero-content">
            <span className="eyebrow">YOUR NEXT EXPERIENCE STARTS HERE</span>
            <h1>Make plans.<br /><span>Make memories.</span></h1>
            <p>
              Discover events, find your seats, and book experiences
              worth looking forward to.
            </p>
            <button
              className="button button-primary"
              onClick={() => {
                setView('events')
                setSelectedEvent(null)
                document.getElementById('events')?.scrollIntoView({
                  behavior: 'smooth',
                })
              }}
            >
              Explore events <span aria-hidden="true">→</span>
            </button>
          </div>
          <div className="hero-decoration" aria-hidden="true">
            <div className="hero-circle circle-one" />
            <div className="hero-circle circle-two" />
            <div className="hero-ticket">
              <span>YOUR NEXT EVENT</span>
              <strong>LIVE IT.</strong>
              <span>NOT JUST WATCH IT.</span>
              <div className="ticket-line" />
              <span className="ticket-code">ADMIT ONE · 2026</span>
            </div>
          </div>
        </section>

        <div className="content-layout">
          <section className="main-content" id="events">
            {error && (
              <div className="alert alert-error" role="alert">
                {error}
                <button onClick={() => setError('')} aria-label="Dismiss error">
                  ×
                </button>
              </div>
            )}

            {notice && (
              <div className="alert alert-success" role="status">
                {notice}
                <button onClick={() => setNotice('')} aria-label="Dismiss message">
                  ×
                </button>
              </div>
            )}

            {view === 'events' && (
              <>
                {selectedEvent ? (
                  <div className="detail-panel">
                    <button
                      className="back-link"
                      onClick={() => setSelectedEvent(null)}
                    >
                      ← Back to events
                    </button>

                    <span className="eyebrow">EVENT DETAILS</span>
                    <h2>{selectedEvent.title}</h2>
                    <p className="detail-description">
                      {selectedEvent.description || 'Join us for this event.'}
                    </p>

                    <div className="detail-grid">
                      <div>
                        <span>Date and time</span>
                        <strong>{formatDate(selectedEvent.starts_at)}</strong>
                      </div>
                      <div>
                        <span>Venue</span>
                        <strong>
                          {getVenue(selectedEvent.venue_id)?.name ?? 'Venue information unavailable'}
                        </strong>
                      </div>
                      <div>
                        <span>Location</span>
                        <strong>
                          {getVenue(selectedEvent.venue_id)?.city ?? '—'}
                        </strong>
                      </div>
                      <div>
                        <span>Ticket price</span>
                        <strong>{formatPrice(selectedEvent.price)}</strong>
                      </div>
                    </div>

                    <div className="booking-notice">
                      <strong>Ready to book?</strong>
                      <p>
                        Seat selection and reservation checkout are the next
                        integration step. No payment will be taken here.
                      </p>
                      {!user && (
                        <button
                          className="button button-primary"
                          onClick={() => {
                            setAuthMode('login')
                            document.getElementById('auth-panel')?.scrollIntoView({
                              behavior: 'smooth',
                            })
                          }}
                        >
                          Sign in to continue
                        </button>
                      )}
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="section-heading">
                      <div>
                        <span className="eyebrow">FIND YOUR NEXT EXPERIENCE</span>
                        <h2>Upcoming events</h2>
                      </div>
                      <span className="result-count">
                        {events.length} events
                      </span>
                    </div>

                    {loading ? (
                      <div className="empty-state">Loading events...</div>
                    ) : events.length === 0 ? (
                      <div className="empty-state">
                        <h3>No events available yet</h3>
                        <p>Check back later for upcoming events.</p>
                      </div>
                    ) : (
                      <div className="event-grid">
                        {events.map((item) => {
                          const venue = getVenue(item.venue_id)

                          return (
                            <article className="event-card" key={item.id}>
                              <div className="event-art">
                                <span className="event-art-label">EVENT #{item.id}</span>
                                <span className="event-art-symbol">✳</span>
                                <span className="event-art-bottom">MAKE IT COUNT</span>
                              </div>

                              <div className="event-card-body">
                                <span className="event-date">
                                  {formatDate(item.starts_at)}
                                </span>
                                <h3>{item.title}</h3>
                                <p className="event-venue">
                                  {venue?.name ?? 'Venue'} · {venue?.city ?? 'Location'}
                                </p>
                                <p className="event-description">
                                  {item.description || 'Discover this upcoming experience.'}
                                </p>
                                <div className="event-card-footer">
                                  <strong>{formatPrice(item.price)}</strong>
                                  <button
                                    className="button button-outline button-small"
                                    onClick={() => {
                                      setSelectedEvent(item)
                                      setError('')
                                    }}
                                  >
                                    View details
                                  </button>
                                </div>
                              </div>
                            </article>
                          )
                        })}
                      </div>
                    )}
                  </>
                )}
              </>
            )}

            {view === 'bookings' && (
              <section className="bookings-section">
                <div className="section-heading">
                  <div>
                    <span className="eyebrow">YOUR ACTIVITY</span>
                    <h2>My bookings</h2>
                  </div>
                  <button
                    className="button button-outline button-small"
                    onClick={() => token && void loadBookings(token)}
                  >
                    Refresh
                  </button>
                </div>

                {reservations.length === 0 ? (
                  <div className="empty-state">
                    <h3>No bookings yet</h3>
                    <p>Your reservations will appear here.</p>
                    <button
                      className="button button-primary"
                      onClick={() => setView('events')}
                    >
                      Explore events
                    </button>
                  </div>
                ) : (
                  <div className="booking-list">
                    {reservations.map((reservation) => {
                      const event = events.find(
                        (item) => item.id === reservation.event_id,
                      )

                      return (
                        <article className="booking-card" key={reservation.id}>
                          <div className="booking-card-top">
                            <div>
                              <span className="event-date">
                                BOOKING #{reservation.id}
                              </span>
                              <h3>{event?.title ?? `Event #${reservation.event_id}`}</h3>
                            </div>
                            <span className={`status status-${reservation.status}`}>
                              {reservation.status}
                            </span>
                          </div>

                          <p className="booking-meta">
                            Booked on {formatDate(reservation.created_at)}
                          </p>

                          <div className="booking-seats">
                            {reservation.seats.map((seat) => (
                              <span key={seat.event_seat_id}>
                                {seat.row_label}{seat.seat_number}
                              </span>
                            ))}
                          </div>

                          <div className="booking-card-footer">
                            <strong>{formatPrice(reservation.total_amount)}</strong>
                            {reservation.status === 'pending' && (
                              <button
                                className="button button-danger button-small"
                                onClick={() => void handleCancel(reservation.id)}
                              >
                                Cancel reservation
                              </button>
                            )}
                          </div>
                        </article>
                      )
                    })}
                  </div>
                )}
              </section>
            )}
          </section>

          {!user && view === 'events' && (
            <aside className="auth-panel" id="auth-panel">
              <span className="eyebrow">GET STARTED</span>
              <h2>{authMode === 'login' ? 'Welcome back' : 'Create your account'}</h2>
              <p>
                {authMode === 'login'
                  ? 'Sign in to manage your event bookings.'
                  : 'Create an account to start booking events.'}
              </p>

              <div className="auth-tabs">
                <button
                  className={authMode === 'login' ? 'auth-tab active' : 'auth-tab'}
                  onClick={() => {
                    setAuthMode('login')
                    setError('')
                  }}
                >
                  Sign in
                </button>
                <button
                  className={authMode === 'register' ? 'auth-tab active' : 'auth-tab'}
                  onClick={() => {
                    setAuthMode('register')
                    setError('')
                  }}
                >
                  Register
                </button>
              </div>

              <form onSubmit={(event) => void handleAuth(event)}>
                <label htmlFor="email">Email address</label>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />

                <label htmlFor="password">Password</label>
                <input
                  id="password"
                  type="password"
                  autoComplete={
                    authMode === 'login' ? 'current-password' : 'new-password'
                  }
                  placeholder="At least 8 characters"
                  minLength={authMode === 'register' ? 8 : undefined}
                  maxLength={128}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                />

                <button
                  className="button button-primary auth-submit"
                  type="submit"
                  disabled={authLoading}
                >
                  {authLoading
                    ? 'Please wait...'
                    : authMode === 'login'
                      ? 'Sign in'
                      : 'Create account'}
                </button>
              </form>

              <p className="auth-footnote">
                Your account is secured using backend authentication.
              </p>
            </aside>
          )}

          {user && view === 'events' && (
            <aside className="side-panel">
              <span className="eyebrow">YOUR ACCOUNT</span>
              <h3>You're signed in</h3>
              <p>{user.email}</p>
              <button
                className="button button-outline"
                onClick={() => setView('bookings')}
              >
                View my bookings
              </button>
            </aside>
          )}
        </div>
      </main>

      <footer className="footer">
        <span className="brand">
          <span className="brand-mark">E</span>
          <span>Event<span className="brand-light">ly</span></span>
        </span>
        <p>Built for experiences worth remembering.</p>
        <span>© 2026 Evently</span>
      </footer>
    </div>
  )
}

export default App

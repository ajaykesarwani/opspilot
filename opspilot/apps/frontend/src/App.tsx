import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api, ApiError, PRIORITIES, SETTLED } from './api'
import type { Priority, Recommendation, RequestDetail } from './api'

const POLL_INTERVAL_MS = 2000
const MAX_CONSECUTIVE_POLL_ERRORS = 5

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback
}

function RecommendationView({ rec }: { rec: Recommendation }) {
  return (
    <div className="recommendation-box">
      <h3>Recommendation</h3>
      <p>{rec.summary}</p>
      <p>
        <strong>Next step:</strong> {rec.recommended_next_step}
      </p>
      {rec.missing_information && (
        <p>
          <strong>Missing information:</strong> {rec.missing_information}
        </p>
      )}
      <p>
        <strong>Confidence:</strong> {rec.confidence_category.replace('_', ' ')}
      </p>
      {rec.citations.length > 0 && (
        <p className="citations">
          <strong>Sources:</strong> {rec.citations.join(', ')}
        </p>
      )}
      <p className="citations">{rec.limitation_disclaimer}</p>
    </div>
  )
}

function App() {
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [priority, setPriority] = useState<Priority>('low')
  const [submitting, setSubmitting] = useState(false)
  const [approving, setApproving] = useState(false)
  const [error, setError] = useState('')
  const [detail, setDetail] = useState<RequestDetail | null>(null)
  const [pollErrors, setPollErrors] = useState(0)

  const requestId = detail?.request_id
  const status = detail?.status
  const settled = status !== undefined && SETTLED.includes(status)
  const polling = requestId !== undefined && !settled && pollErrors < MAX_CONSECUTIVE_POLL_ERRORS

  useEffect(() => {
    if (!polling || !requestId) return
    const timer = setInterval(() => {
      api
        .getRequest(requestId)
        .then((next) => {
          setDetail(next)
          setPollErrors(0)
        })
        .catch(() => setPollErrors((n) => n + 1))
    }, POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [polling, requestId])

  const handleSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault()
      setSubmitting(true)
      setError('')
      try {
        const accepted = await api.submitRequest({
          subject,
          body,
          requester: 'local_demo_user',
          priority,
        })
        setDetail(await api.getRequest(accepted.request_id))
        setPollErrors(0)
        setSubject('')
        setBody('')
      } catch (err) {
        setError(errorMessage(err, 'Error submitting request'))
      } finally {
        setSubmitting(false)
      }
    },
    [subject, body, priority],
  )

  const handleApprove = async () => {
    if (!requestId) return
    setApproving(true)
    setError('')
    try {
      await api.approveRequest(requestId)
      setDetail(await api.getRequest(requestId))
    } catch (err) {
      setError(errorMessage(err, 'Error approving request'))
    } finally {
      setApproving(false)
    }
  }

  const fillDemo = () => {
    setSubject('Account question')
    setBody('How long does account deletion take, and can it be reversed?')
    setPriority('normal')
  }

  const reached = (...states: string[]) => status !== undefined && states.includes(status)
  const recommendation = detail?.result?.recommendation

  return (
    <div className="app-container">
      <header className="header">
        <h1>OpsPilot</h1>
        <div className="demo-badge">Local Demo Environment</div>
      </header>

      <div className="grid">
        <div className="card">
          <h2>Submit Request</h2>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label htmlFor="subject">Subject</label>
              <input
                id="subject"
                className="form-control"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                minLength={3}
                maxLength={200}
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="body">Body</label>
              <textarea
                id="body"
                className="form-control"
                rows={4}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                minLength={10}
                maxLength={10000}
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="priority">Priority</label>
              <select
                id="priority"
                className="form-control"
                value={priority}
                onChange={(e) => setPriority(e.target.value as Priority)}
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {p[0].toUpperCase() + p.slice(1)}
                  </option>
                ))}
              </select>
            </div>

            <button type="submit" className="btn" disabled={submitting}>
              {submitting ? <div className="spinner" /> : 'Submit Workflow'}
            </button>
            <button type="button" className="btn btn-secondary" onClick={fillDemo}>
              Fill Demo Data
            </button>

            {error && (
              <div role="alert" className="form-error">
                {error}
              </div>
            )}
          </form>
        </div>

        <div className="card">
          <h2>Workflow Status</h2>

          {!detail && (
            <div className="empty-state">No active request. Submit one to see its status here.</div>
          )}

          {detail && (
            <div>
              <span className={`status-badge status-${detail.status}`}>{detail.status}</span>
              <div className="meta">ID: {detail.request_id}</div>
              {pollErrors >= MAX_CONSECUTIVE_POLL_ERRORS && (
                <div role="alert" className="form-error">
                  Lost contact with the API; status may be stale. Reload to retry.
                </div>
              )}

              <div className="timeline">
                <div className="timeline-item">
                  <strong>Received</strong>
                  <div className="meta">{new Date(detail.created_at).toLocaleString()}</div>
                </div>
                {reached('QUEUED', 'PROCESSING', 'AWAITING_REVIEW', 'COMPLETED', 'FAILED', 'DEAD_LETTERED') && (
                  <div className="timeline-item">
                    <strong>Queued</strong>
                  </div>
                )}
                {reached('PROCESSING', 'AWAITING_REVIEW', 'COMPLETED', 'FAILED', 'DEAD_LETTERED') && (
                  <div className="timeline-item">
                    <strong>Processing</strong>
                  </div>
                )}
                {reached('AWAITING_REVIEW', 'COMPLETED') && (
                  <div className="timeline-item">
                    <strong>Recommendation ready</strong>
                  </div>
                )}
                {reached('FAILED', 'DEAD_LETTERED') && (
                  <div className="timeline-item">
                    <strong>Could not be processed</strong>
                    <div className="meta">{detail.error_code ?? detail.result?.error}</div>
                  </div>
                )}
              </div>

              {recommendation && <RecommendationView rec={recommendation} />}

              {detail.status === 'AWAITING_REVIEW' && (
                <div className="review-box">
                  <h3>Human Review Required</h3>
                  <p>Nothing is applied until you approve this recommendation.</p>
                  <button className="btn btn-success" onClick={handleApprove} disabled={approving}>
                    {approving ? 'Approving…' : 'Approve & Complete'}
                  </button>
                </div>
              )}
              <p className="meta">{detail.disclaimer}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default App

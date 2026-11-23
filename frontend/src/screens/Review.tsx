import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { apiFetch, jsonBody } from '../api/client'
import { REVIEWABLE, STATUS_LABEL, type Result } from '../api/grading'

type Action = 'accept' | 'edit' | 'reject' | 'undo_reject' | 'manual'

function reviewNote(r: Result): string {
  if (r.status === 'PUBLISHED') return 'Published to Canvas. To change this grade, edit it in Canvas.'
  if (r.status === 'APPROVED' || r.status === 'PUBLISHING') return 'Approved. Ready to publish.'
  if (r.status === 'PUBLISH_ERROR_MANUAL_REVIEW') return 'Publish failed. Check Canvas, then retry from the dashboard.'
  if (r.status === 'REJECTED') return 'Suggestion rejected. It will not be published unless you enter a manual grade.'
  if (r.final_score !== null) return 'Review saved. This grade has not been published to Canvas.'
  return 'Not reviewed yet.'
}

export default function Review() {
  const { resultId } = useParams()
  const [result, setResult] = useState<Result>()
  const [points, setPoints] = useState<Record<string, string>>({})
  const [feedback, setFeedback] = useState('')
  const [error, setError] = useState<string>()
  const [saving, setSaving] = useState(false)

  function show(r: Result) {
    const suggestion = r.review_action === 'rejected' ? null : r
    setResult(r)
    const ai = new Map(suggestion?.ai_output?.criteria.map((c) => [c.criterion_id, c.awarded_points]))
    setPoints(
      Object.fromEntries(
        r.criteria.map((c) => [c.criterion_id, String(r.final_criteria?.[c.criterion_id] ?? ai.get(c.criterion_id) ?? '')]),
      ),
    )
    setFeedback(r.final_feedback ?? suggestion?.suggested_feedback ?? '')
  }

  useEffect(() => {
    apiFetch<Result>(`/api/grading/results/${resultId}`).then(show, (e: Error) => setError(e.message))
  }, [resultId])

  if (!result) return error ? <p role="alert">{error}</p> : <p>Loading...</p>
  const { criteria, max_score: max } = result
  const ai = new Map(result.ai_output?.criteria.map((c) => [c.criterion_id, c]))
  const scored = criteria.some((c) => points[c.criterion_id].trim())
  const total = Math.round(criteria.reduce((sum, c) => sum + Number(points[c.criterion_id]), 0) * 100) / 100

  async function save(action: Action) {
    const edited =
      feedback !== result!.suggested_feedback ||
      criteria.some((c) => Number(points[c.criterion_id]) !== ai.get(c.criterion_id)?.awarded_points)
    if (action === 'accept' && edited && !confirm('Replace your edited scores and feedback with the AI suggestion?')) return
    if (action === 'undo_reject' && result!.final_score !== null && !confirm('Remove the manual grade you saved?')) return
    const graded = action === 'edit' || action === 'manual'
    if (graded) {
      const bad = criteria.find((c) => {
        const n = Number(points[c.criterion_id])
        return !points[c.criterion_id].trim() || !(n >= 0 && n <= c.max_points)
      })
      if (bad) return setError(`${bad.title} must be between 0 and ${bad.max_points}.`)
    }
    setSaving(true)
    setError(undefined)
    try {
      const body = graded ? { action, criterion_scores: points, feedback } : { action }
      show(await apiFetch<Result>(`/api/grading/results/${resultId}/review`, jsonBody('PATCH', body)))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const editable = REVIEWABLE.has(result.status) && !saving
  const rejected = result.review_action === 'rejected'
  const canAccept = result.suggested_score !== null && !rejected
  return (
    <>
      <p>
        <Link to={`/batches/${result.batch_id}`}>Back to dashboard</Link>
      </p>
      <h2>{result.student_name}</h2>
      <p>
        Attempt {result.attempt}, {result.file_type || 'no file'}. Status: {STATUS_LABEL[result.status]}.
      </p>
      {result.error && <p role="alert">{result.error}.</p>}

      <h3>Submission</h3>
      <pre className="submission">{result.submission_text ?? 'No submission text is available.'}</pre>

      <h3>AI suggestion</h3>
      {result.suggested_score === null ? (
        <p>
          {result.status === 'PUBLISHED'
            ? 'Scores and feedback are removed once a grade is published.'
            : result.status === 'AI_ERROR_MANUAL_REVIEW'
              ? 'No AI suggestion. Nothing was published. Grade this submission manually.'
              : 'No AI suggestion yet.'}
        </p>
      ) : (
        <p>
          Suggested score: {result.suggested_score} / {max}. {result.suggested_feedback}
        </p>
      )}
      {result.ai_output?.manual_review_required && (
        <p role="alert">The AI could not evaluate part of this submission reliably. Check it closely.</p>
      )}
      {!!result.ai_output?.warnings.length && (
        <ul>
          {result.ai_output.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
      <table>
        <thead>
          <tr>
            <th>Criterion</th>
            <th>Max</th>
            <th>AI score</th>
            <th>Rationale</th>
            <th>Feedback</th>
            <th>Final score</th>
          </tr>
        </thead>
        <tbody>
          {criteria.map((c) => (
            <tr key={c.criterion_id}>
              <td>
                {c.title}
                {c.description && <small>{c.description}</small>}
              </td>
              <td>{c.max_points}</td>
              <td>{ai.get(c.criterion_id)?.awarded_points ?? '-'}</td>
              <td>{ai.get(c.criterion_id)?.rationale}</td>
              <td>{ai.get(c.criterion_id)?.feedback}</td>
              <td>
                <input
                  type="number"
                  aria-label={`Final score for ${c.title}`}
                  min={0}
                  max={c.max_points}
                  step="any"
                  value={points[c.criterion_id]}
                  disabled={!editable}
                  onChange={(e) => setPoints({ ...points, [c.criterion_id]: e.target.value })}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Final grade</h3>
      <p>
        Total: {scored ? total : '-'} / {max}
      </p>
      <label>
        Feedback for the student (optional)
        <textarea rows={5} value={feedback} disabled={!editable} onChange={(e) => setFeedback(e.target.value)} />
      </label>
      {error && <p role="alert">{error}</p>}
      {canAccept ? (
        <>
          <button onClick={() => save('accept')} disabled={!editable}>
            Accept AI suggestion
          </button>
          <button onClick={() => save('edit')} disabled={!editable}>
            Save edits
          </button>
          <button onClick={() => save('reject')} disabled={!editable}>
            Reject suggestion
          </button>
        </>
      ) : (
        <>
          <button onClick={() => save('manual')} disabled={!editable}>
            Save manual grade
          </button>
          {rejected && (
            <button onClick={() => save('undo_reject')} disabled={!editable}>
              Undo reject
            </button>
          )}
        </>
      )}
      <p role="status">{reviewNote(result)}</p>
      <p>Grades are sent to Canvas only after you approve and publish them from the dashboard.</p>
    </>
  )
}

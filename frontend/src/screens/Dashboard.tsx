import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { apiFetch, jsonBody } from '../api/client'
import { REVIEWABLE, STATUS_LABEL, type Batch, type ResultRow, type Status } from '../api/grading'

interface Outcome {
  result_id: string
  ok: boolean
  message?: string
}

const ACTIVE = new Set<Status>(['READY_FOR_GRADING', 'BEING_GRADED', 'PUBLISHING'])

const publishable = (r: ResultRow) => r.status === 'AWAITING_REVIEW' && r.final_score !== null

export default function Dashboard() {
  const { batchId } = useParams()
  const [batch, setBatch] = useState<Batch>()
  const [error, setError] = useState<string>()
  const [selected, setSelected] = useState(new Set<string>())
  const [outcomes, setOutcomes] = useState<Outcome[]>()
  const [publishing, setPublishing] = useState(false)

  const load = useCallback(
    () =>
      apiFetch<Batch>(`/api/grading/batches/${batchId}`).then(
        (b) => {
          setBatch(b)
          setError(undefined)
        },
        (e: Error) => setError(e.message),
      ),
    [batchId],
  )
  const active = batch?.results.some((r) => ACTIVE.has(r.status)) ?? true
  useEffect(() => {
    load()
    if (!active) return
    const timer = setInterval(load, 3000)
    return () => clearInterval(timer)
  }, [load, active])

  async function publish() {
    if (!confirm(`Publish ${selected.size} grade(s) to Canvas? A published grade cannot be published again.`)) return
    setPublishing(true)
    try {
      const body = jsonBody('POST', { result_ids: [...selected] })
      setOutcomes((await apiFetch<{ outcomes: Outcome[] }>(`/api/grading/batches/${batchId}/approve-and-publish`, body)).outcomes)
      setSelected(new Set())
      await load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setPublishing(false)
    }
  }

  function toggle(id: string) {
    const next = new Set(selected)
    if (!next.delete(id)) next.add(id)
    setSelected(next)
  }

  if (!batch) return error ? <p role="alert">{error}</p> : <p>Loading...</p>
  const name = (id: string) => batch.results.find((r) => r.id === id)?.student_name ?? id
  return (
    <>
      <h2>{batch.assignment_name}</h2>
      <p>
        <Link to="/">New grading run</Link>
      </p>
      <ul className="counts">
        <li>Total {batch.counts.total}</li>
        <li>Pending AI {batch.counts.pending_ai}</li>
        <li>Ready for review {batch.counts.ready_for_review}</li>
        <li>Approved {batch.counts.approved}</li>
        <li>Failed {batch.counts.failed}</li>
      </ul>
      {error && <p role="alert">{error}</p>}
      <table>
        <thead>
          <tr>
            <th>Select</th>
            <th>Student</th>
            <th>File type</th>
            <th>AI score</th>
            <th>Final score</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {batch.results.map((r) => (
            <tr key={r.id}>
              <td>
                <input
                  type="checkbox"
                  aria-label={`Select ${r.student_name}`}
                  checked={selected.has(r.id)}
                  disabled={!publishable(r)}
                  onChange={() => toggle(r.id)}
                />
              </td>
              <td>{r.student_name}</td>
              <td>{r.file_type || '-'}</td>
              <td>{r.suggested_score ?? '-'}</td>
              <td>{r.final_score ?? '-'}</td>
              <td>
                {STATUS_LABEL[r.status]}
                {r.error && <small>{r.error}</small>}
              </td>
              <td>
                <Link to={`/results/${r.id}`}>
                  {r.status === 'AI_ERROR_MANUAL_REVIEW' ? 'Grade manually' : REVIEWABLE.has(r.status) ? 'Review' : 'Details'}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button onClick={publish} disabled={publishing || selected.size === 0}>
        Approve and publish selected ({selected.size})
      </button>
      {outcomes && (
        <div role="status">
          <p>
            {outcomes.length} selected, {outcomes.filter((o) => o.ok).length} publishing. Their final status shows in
            the table.
          </p>
          <ul>
            {outcomes
              .filter((o) => !o.ok)
              .map((o) => (
                <li key={o.result_id}>
                  {name(o.result_id)}: {o.message}
                </li>
              ))}
          </ul>
        </div>
      )}
      <p>
        Data is deleted 48 hours after upload or after publish. This batch is deleted by{' '}
        {new Date(batch.expires_at).toLocaleString()}.
      </p>
    </>
  )
}

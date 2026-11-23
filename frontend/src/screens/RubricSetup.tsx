import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { apiFetch, jsonBody } from '../api/client'
import type { Criterion } from '../api/grading'

interface Course {
  id: string
  name: string
}

interface Assignment {
  id: string
  name: string
  points_possible: number
  submission_types: string[]
  supported: boolean
}

interface Rubric {
  criteria: Criterion[]
  max_score: number
}

const EXAMPLE = `Correctness: 10 Produces the expected output
Style: 5 [keywords: comments, naming] Readable, well-named code
Total: 15`

export default function RubricSetup() {
  const navigate = useNavigate()
  const [courses, setCourses] = useState<Course[] | Error>()
  const [courseId, setCourseId] = useState('')
  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [assignmentId, setAssignmentId] = useState('')
  const [text, setText] = useState('')
  const [rubric, setRubric] = useState<Rubric>()
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)

  const loadCourses = () => apiFetch<Course[]>('/api/canvas/courses').then(setCourses, setCourses)
  useEffect(() => {
    loadCourses()
  }, [])

  useEffect(() => {
    if (!courseId) return
    let staleCourse = false
    apiFetch<Assignment[]>(`/api/canvas/courses/${courseId}/assignments`).then(
      (list) => staleCourse || setAssignments(list),
      (e: Error) => staleCourse || setError(e.message),
    )
    return () => {
      staleCourse = true
    }
  }, [courseId])

  async function run(task: () => Promise<void>) {
    setBusy(true)
    setError(undefined)
    try {
      await task()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const loadFile = (file: File) =>
    run(async () => {
      setRubric(undefined)
      const name = file.name.toLowerCase()
      if (name.endsWith('.txt')) {
        setText(await file.text())
      } else if (name.endsWith('.pdf')) {
        setText((await apiFetch<{ rubric_text: string }>('/api/grading/rubric/pdf', { method: 'POST', body: file })).rubric_text)
      } else {
        throw new Error('Unsupported file type: upload a PDF or TXT rubric.')
      }
    })

  const check = () =>
    run(async () => setRubric(await apiFetch<Rubric>('/api/grading/rubric/preview', jsonBody('POST', { rubric_text: text }))))

  const start = () =>
    run(async () => {
      const body = { course_id: courseId, assignment_id: assignmentId, rubric_text: text }
      const { batch_id } = await apiFetch<{ batch_id: string }>('/api/grading/batches', jsonBody('POST', body))
      navigate(`/batches/${batch_id}`)
    })

  if (courses === undefined) return <p>Connecting to Canvas...</p>
  if (courses instanceof Error) {
    return (
      <>
        <p role="alert">Canvas: {courses.message}</p>
        <button
          onClick={() => {
            setCourses(undefined)
            loadCourses()
          }}
        >
          Try again
        </button>
      </>
    )
  }

  const assignment = assignments.find((a) => a.id === assignmentId)
  const mismatch = rubric && assignment && rubric.max_score !== assignment.points_possible
  return (
    <>
      <h2>Rubric setup</h2>
      <p>Canvas connected.</p>
      <label>
        Course
        <select
          value={courseId}
          onChange={(e) => {
            setCourseId(e.target.value)
            setAssignments([])
            setAssignmentId('')
          }}
        >
          <option value="">Select a course</option>
          {courses.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Assignment
        <select value={assignmentId} onChange={(e) => setAssignmentId(e.target.value)} disabled={!courseId}>
          <option value="">Select an assignment</option>
          {assignments.map((a) => (
            <option key={a.id} value={a.id} disabled={!a.supported}>
              {a.name}
              {!a.supported && ' (submission type not supported)'}
            </option>
          ))}
        </select>
      </label>
      {assignment && (
        <p>
          Worth {assignment.points_possible} points. Submission types: {assignment.submission_types.join(', ')}.
        </p>
      )}
      <label>
        Rubric, one criterion per line
        <textarea
          rows={8}
          value={text}
          placeholder={EXAMPLE}
          onChange={(e) => {
            setText(e.target.value)
            setRubric(undefined)
          }}
        />
      </label>
      <label>
        Or upload a rubric file (.pdf or .txt)
        <input type="file" accept=".pdf,.txt" onChange={(e) => e.target.files?.[0] && loadFile(e.target.files[0])} />
      </label>
      <button onClick={check} disabled={busy || !text.trim()}>
        Check rubric
      </button>
      {rubric && (
        <>
          <table>
            <thead>
              <tr>
                <th>Criterion</th>
                <th>Max points</th>
                <th>Parsed expectation</th>
              </tr>
            </thead>
            <tbody>
              {rubric.criteria.map((c) => (
                <tr key={c.criterion_id}>
                  <td>{c.title}</td>
                  <td>{c.max_points}</td>
                  <td>
                    {c.description}
                    {c.keywords.length > 0 && ` (keywords: ${c.keywords.join(', ')})`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p role="status">
            {rubric.criteria.length} criteria, {rubric.max_score} points total.
            {mismatch && ` The assignment is worth ${assignment.points_possible} points; fix the rubric before grading.`}
          </p>
        </>
      )}
      {error && <p role="alert">{error}</p>}
      {!assignment && <p>Select an assignment before starting grading.</p>}
      <button onClick={start} disabled={busy || !assignment?.supported || !rubric || !!mismatch}>
        Start grading
      </button>
    </>
  )
}

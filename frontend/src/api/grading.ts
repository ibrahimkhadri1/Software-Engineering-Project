export interface Criterion {
  criterion_id: string
  title: string
  description: string
  max_points: number
  keywords: string[]
}

export interface ResultRow {
  id: string
  student_name: string
  file_type: string
  status: Status
  suggested_score: number | null
  final_score: number | null
  error: string | null
}

export interface Batch {
  id: string
  assignment_name: string
  expires_at: string
  max_score: number
  counts: Record<'total' | 'pending_ai' | 'ready_for_review' | 'approved' | 'failed', number>
  results: ResultRow[]
}

export interface Result extends ResultRow {
  batch_id: string
  attempt: string
  submission_text: string | null
  criteria: Criterion[]
  max_score: number
  ai_output: {
    criteria: { criterion_id: string; awarded_points: number; rationale: string; feedback: string }[]
    warnings: string[]
    manual_review_required: boolean
  } | null
  suggested_feedback: string | null
  final_feedback: string | null
  review_action: 'pending' | 'accepted' | 'edited' | 'rejected'
}

export const STATUS_LABEL = {
  READY_FOR_GRADING: 'Waiting for AI',
  BEING_GRADED: 'Being graded',
  AWAITING_REVIEW: 'Ready for review',
  REJECTED: 'Suggestion rejected',
  APPROVED: 'Approved',
  PUBLISHING: 'Publishing',
  PUBLISHED: 'Published to Canvas',
  AI_ERROR_MANUAL_REVIEW: 'Needs a manual grade',
  PUBLISH_ERROR_MANUAL_REVIEW: 'Publish failed: check Canvas',
}

export type Status = keyof typeof STATUS_LABEL

export const REVIEWABLE = new Set<Status>(['AWAITING_REVIEW', 'REJECTED', 'AI_ERROR_MANUAL_REVIEW'])

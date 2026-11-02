# Canvas Autograder

An AI-assisted grading tool for Canvas, built by team iCANDY for CMPE 131 (Fall 2026). A professor or TA picks a
Canvas assignment and a rubric, the system suggests a score and feedback for each submission using Amazon Bedrock,
and staff review, edit or reject every suggestion. Only approved grades are published to Canvas.

- **Frontend:** React + TypeScript + Vite (`frontend/`)
- **Backend:** FastAPI + SQLAlchemy + PostgreSQL (`backend/`)
- **Services:** Auth0 (sign-in), Canvas REST API, Amazon Bedrock (Claude Sonnet 4.5)

**Current build (alpha):** sign-in uses the real Auth0 tenant and Canvas is a fake built into the backend, so no Canvas
account is needed and no real grades are posted. The AI grader is a fake by default, so no AWS account is needed and
the scores are not real AI output. [Real AI grading](#real-ai-grading) turns on Amazon Bedrock.

## Run it locally

Requirements: [Docker Desktop](https://www.docker.com/products/docker-desktop/) (running),
[uv](https://docs.astral.sh/uv/) (Python 3.13), Node.js 24. The commands work in PowerShell and in Bash.

```sh
# 1. Database (from the repo root)
docker compose up -d --wait db

# 2. Backend
cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# 3. Frontend (second terminal)
cd frontend
cp .env.example .env.local
npm install
npm run dev                 # http://localhost:5173
```

Check: `http://localhost:8000/healthz` returns `{"status":"ok"}` and `http://localhost:5173` shows a **Log in** button.

| Problem | Cause and fix |
|---|---|
| `npm.ps1 cannot be loaded` in PowerShell | Script execution is off on the machine. Use `npm.cmd` in place of `npm`. |
| Auth0 callback error after logging in | Auth0 only allows `http://localhost:5173`. Vite picks another port if 5173 is taken; stop whatever holds it. |
| A route answers 404 "Not Found" or the backend cannot bind | An old server holds port 8000. Stop it and start the backend again. |

## Test accounts

Logins are shared privately by the developer. Sign-in requires a verified `@sjsu.edu` email.

| Account | Expected result |
|---|---|
| `@sjsu.edu` with the Grader role | Reaches Rubric setup |
| `@sjsu.edu` without the role (the student case) | "Your account does not have grader access." |
| Any other email | Auth0 refuses the login |

## Test data

The fake course is **CMPE 131 Sandbox (fake)**. **Lab 3: Recursion** is worth 21 points and has the seven submissions
below. **Midterm (on paper)** cannot be selected for grading because of its submission type. A rubric that does not
total 21 points blocks **Start grading**.

Sample rubric, which gives the AI scores in the table:

```text
Correctness: 10 points - Program produces the right output
Style: 5 pts
Concepts: 6 [keywords: loop, recursion, base case; 2 each] names the key ideas
Total: 21
```

| Student | Submission | AI score | What it exercises |
|---|---|---|---|
| Ada Lovelace | online text | 19 | Normal flow; partial keyword credit |
| Alan Turing | `.py` | 19 | Normal flow; the file is read as text, never run |
| Grace Hopper | `.java` | 17 | Every publish fails: three tries, then "Publish failed: check Canvas" |
| Edsger Dijkstra | `.pdf` | 21 | PDF text extraction; every keyword found |
| Barbara Liskov | `.jpeg` | none | Rejected before any AI call: "unsupported file type" |
| Donald Knuth | online text | none | Malformed AI output: "AI output invalid after 3 attempts" |
| Margaret Hamilton | `.txt` | none | AI score over the maximum: "AI output invalid after 3 attempts" |

Rubric format: one criterion per line, `Title: <points> [keywords: a, b, c; <n> each] <description>`. The keyword part
and the description are optional, and so is a final `Total: <points>` line. The fake grader gives full points on
criteria without keywords. Criteria with keywords are always scored by keyword matching, with either grader.

**Starting over:** a student's grade can only be published once, across all grading runs, until the data expires. To
publish the same students again, stop the backend, wipe the local database and recreate its tables, then start the
backend again:

```sh
docker compose down -v
docker compose up -d --wait db
cd backend
uv run alembic upgrade head
```

**Testing data deletion:** set `DATA_TTL_HOURS=0` in `backend/.env` and start the backend, then create a grading run
and restart the backend. The deletion sweep runs at startup and every 10 minutes, so reloading the run's page shows
"Not found". Afterwards set it back to 48 and restart the backend.

## Real AI grading

With `AI_MODE=bedrock` and an AWS key in `backend/.env`, the backend sends each submission to Claude Sonnet 4.5 on
Amazon Bedrock. Every call costs money, so the default stays `fake`, and the automated tests always use the fake. The
scores in the table above then come from the model and can differ, and Donald's and Margaret's markers no longer force
a failure. Each call logs its token counts as a `bedrock call` line.

| Situation | Status | Message on the Review page |
|---|---|---|
| Bedrock unreachable, throttled or refusing the key on all three tries | Needs a manual grade | "AI service unavailable after 3 attempts" |
| Model output invalid on all three tries | Needs a manual grade | "AI output invalid after 3 attempts" |
| Submission over 200,000 characters (no AI call) | Needs a manual grade | "Submission too long for AI grading" |
| Model flags the submission as hard to evaluate | Ready for review | A notice and the model's warnings |

## Test cases

Test case numbers are from the Test Plan Document. Backend test files are in `backend/tests/`.

| Test case | Automated test | Check in the browser |
|---|---|---|
| TC-001 Rubric parsing | `test_rubric.py` | **Check rubric** with the sample, then with a line that has no points |
| TC-002 File types | `test_submission.py` | Barbara's `.jpeg` is refused, the other types are graded |
| TC-003 AI output validation | `test_bedrock_val.py` | Margaret's over-maximum score is refused |
| TC-004 Partial credit | `test_partial_credit.py` | Ada's 19 of 21 with the sample rubric |
| TC-005 Accept, edit, reject | `test_review.py`; `test_grading_api.py`: `test_accepted_result_publishes_once`, `test_edit_keeps_the_ai_suggestion`, `test_rejected_result_can_be_graded_manually_and_published` | Each action on a **Review** page, final score on the dashboard |
| TC-006 Duplicate publish | `test_publish.py`, `test_models.py`; `test_grading_api.py`: `test_the_same_submission_in_a_second_batch_is_not_published_again` | Publish Ada, start a new grading run, accept and publish Ada again: refused |
| TC-007 Login and access | `test_auth.py` | The accounts above |
| TC-008 Invalid AI output | `test_bedrock_val.py`; `test_runner.py`: `test_three_invalid_outputs_end_in_manual_review` | Donald ends in "Needs a manual grade" with no score |
| TC-009 Unapproved publish | `test_publish.py`: `test_only_approved_results_can_be_published`; `test_grading_api.py`: `test_only_reviewed_results_of_the_batch_are_published` | Checkboxes stay disabled until a final score exists |
| TC-010 End to end | `test_grading_api.py`: `test_rubric_to_published_end_to_end` | Sample rubric, edit Alan's score, publish, status "Published to Canvas" |

Also covered: publish retries (`test_publish.py`, `test_runner.py`), the 48-hour purge (`test_retention.py`) and one
grader's runs being hidden from another (`test_grading_api.py`). The frontend has no automated tests yet; browser
checks are planned with Selenium.

Run the automated checks, with the database from step 1 running:

```sh
cd backend
uv run pytest               # fails below 90% coverage

cd ../frontend
npm run lint
npm run build
```

CI runs the backend and frontend checks on every pull request.

## Known issues

Alpha limits:

- Canvas is a fake. "Canvas connected" always shows, there is no Canvas OAuth, and publishes are held in memory.
- The app runs locally only; it is not deployed yet.
- A failed publish has no retry button. Grace Hopper's row stays in "Publish failed: check Canvas" until the data expires.
- A reload may ask for **Log in** again where the browser blocks third-party cookies.
- The Vite build warns that the bundle is over 500 kB. It is only a warning.

Current behaviour:

- Rubrics must follow the format above; anything else gets an error naming the line.
- Student code is read as text and never run.
- The final grade is one total plus feedback. Per-criterion AI scores are shown read-only.
- With real AI grading, a keyword criterion's rationale is the model's own reading and can disagree with the score,
  which always comes from keyword matching.
- Scores are rounded to two decimal places.
- Publishing clears the submission text and feedback. The row keeps its ids, student name and scores until the 48-hour
  deletion, and there is no manual delete button.
- Dashboard counts: **Approved** includes published rows; **Failed** includes rows that need a manual grade.
- Audit records hold the action and ids, not the user who acted.
- Background work runs inside the backend process. After a restart, grading resumes, and a publish that was interrupted
  moves to "Publish failed: check Canvas" because Canvas may already have the grade.
- Approving the same student from two grading runs at the same moment returns a 500 for one of them. Nothing is posted
  twice.

## Configuration

Settings come from environment variables (`backend/.env`, `frontend/.env.local`); the `.env.example` files hold working
local values.

| Backend | Purpose |
|---|---|
| `FRONTEND_ORIGIN` | Origin allowed by CORS |
| `DATABASE_URL` | PostgreSQL connection |
| `LOG_LEVEL` | Log level |
| `GRADE_CONCURRENCY` | Submissions graded at once |
| `DATA_TTL_HOURS` | Hours before a grading run is deleted |
| `AUTH0_DOMAIN`, `AUTH0_AUDIENCE` | Auth0 tenant and API |
| `AI_MODE` | `fake` (default) or `bedrock` |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | AWS key, for `bedrock` only |
| `AWS_REGION`, `BEDROCK_MODEL_ID` | Optional; default to `us-west-2` and the Sonnet 4.5 US inference profile |

| Frontend | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Backend URL |
| `VITE_AUTH0_DOMAIN`, `VITE_AUTH0_CLIENT_ID`, `VITE_AUTH0_AUDIENCE` | Auth0 tenant, app and API |

## Reporting defects

Defects go in GitHub Issues with the fields from section 7.1 of the Test Plan Document. Backend logs are JSON lines in
the backend terminal, without tokens or student content. Every API response has an `X-Correlation-ID` header, which also
appears in the logs and is useful evidence in a report.

## Contributing

Work on a branch and open a pull request to `main`; changes are reviewed before merging.

# StriveTrack prototype

StriveTrack is a local teaching workspace for special-education teachers and case managers. It helps teachers compare an activity with an existing approved goal, inspect quoted evidence when an activity supplies the planning decision, and review a revised activity that preserves the approved accommodations. Teachers approve activities before recording practice sessions with a learner; their observations remain separate from the alignment output. Only teachers use the app.

This prototype uses **synthetic data, simulated sign-in, and optional AI assistance** (see [Responsible AI](#responsible-ai)). Without an API key it runs entirely on local rules. It does not write or change an IEP, diagnose learners, or judge mastery. Cedar Grove is a fictional demo school; the content does not represent research findings or an endorsement from a real school or challenge partner.

## The problem and who it's for

**Problem statement:** Special-education teachers lack time to check whether everyday activities actually practice each learner's IEP goal, so neurodivergent learners with executive-function goals end up following directions instead of building the planning and sequencing skills their goals target.

**Primary user: Ms. Patel, special-education teacher.** She supports 14 learners, each with different IEP goals and accommodations, and has minutes rather than hours to adapt materials. She needs to see quickly whether a worksheet fits a goal, fix it without losing any approved accommodation, and record how practice went.

**Learner who benefits: Jordan, 16, autistic, with an executive-function goal:** "Given three task cards, choose and explain a workable order." Jordan's worksheets say "Follow these steps in order: 1, 2, 3." He completes them perfectly but never practices planning. StriveTrack flags that gap, rewrites the activity as unordered picture cards with his supports kept, and lets his teacher record the order he chose and why.

StriveTrack is used by teachers only; learners benefit through better-aligned activities and never sign in.

## Start the app

Prerequisites:

- Node.js **20.19+ or 22.12+** and npm. Newer supported Node releases work too.
- Python **3.9+**, including `venv` and pip. Setup prefers Python 3.12, then 3.11, 3.10, `python3`, or `python` when available.
- Internet access for the initial dependency installation. The running app requires no external services or API keys.

From this folder, install dependencies and launch both servers:

```sh
cd prototype
npm run setup && npm run dev
```

If your terminal already has `prototype/` as its current directory, omit `cd prototype`. On Windows PowerShell versions that do not support `&&`, run `npm run setup` and `npm run dev` separately.

Open **http://127.0.0.1:5173**. The backend API is at **http://127.0.0.1:8001/api**, with interactive documentation at **http://127.0.0.1:8001/docs**. Press **Ctrl+C** to stop the servers started by that command. After the initial install, `npm run dev` is the only command needed to start the app again. If StriveTrack is already running, the command prints its URLs and exits successfully; open the existing app in your browser.

Setup creates the Python virtual environment at `backend/.venv/`, installs frontend dependencies in `frontend/node_modules/`, and keeps package caches inside `.cache/`. It does not install anything into existing application folders or change parent configuration files.

To turn on AI, put your key in `.env` at the project root (`STRIVETRACK_AI_API_KEY=...`) and restart `npm run dev`. [.env.example](.env.example) lists every setting, including the model name. Shell environment variables take precedence over `.env`. The **Alignment check** screen shows whether AI is on.

## Demo accounts

Choose an account on the login screen, or enter its email. Every account uses the password **`strivetrack-demo`**.

| Name | Email | Demo role |
| --- | --- | --- |
| Maya Brooks | `teacher@strivetrack.demo` | Teacher |
| Casey Nguyen | `casey@strivetrack.demo` | Teacher |
| Elena Rivera | `admin@strivetrack.demo` | Administrator |

Roles identify demo users; this prototype does not implement a production permission system or staff administration. All three accounts share the same synthetic workspace.

## Feature tour

1. **Overview:** summary counts, a weekly activity chart and recent activities. All values come from the backend.
2. **Goal library:** search, filter, sort, paginate, create, edit, archive, and delete goal records. Each record contains its skill description, success criteria, category, due date, and approved accommodations.
3. **Activities:** browse linked worksheets in varied states, including overdue and archived examples. Create or edit a worksheet and associate it with an existing goal, or open it for an alignment check.
4. **Alignment check and review:** inspect the goal, supports, original activity, and quoted evidence. The check looks for activities that do the executive-function work for the learner, such as pre-ordered steps, choices already made, or answers given. Generate a revision (AI-written when enabled), edit it, save it, and approve or reject it. Removing an approved accommodation blocks approval until it is restored; differences in capitalization or spacing do not.
5. **Practice session record:** StriveTrack is used by teachers only. Present an approved version to the learner, arrange the task cards in the order the learner chooses, and record a learner code, how the learner explained the order, the prompting needed, and the supports used. Sessions are listed next to the teacher's observation notes. Learner-facing aids: larger cards, an **Easier reading** mode (Verdana-style font with WCAG 1.4.12 letter, word, and line spacing), read-aloud through the browser’s speech synthesis where a local English voice exists, and a visible **Thinking time** countdown with no score attached.
6. **Activity history:** browse the append-only record of checks, draft edits (including when a support was removed), approvals, rejections, observation edits and deletions, and practice sessions.

A check is flagged **out of date** when the goal (skill, criteria, or supports) or the activity text changes after it ran, so a teacher never relies on an old result.

The interface includes light and dark themes, a desktop sidebar and mobile bottom navigation, keyboard focus indicators, confirmation dialogs, inline form errors, toasts, loading skeletons, empty states, and retry states. It respects the system setting for reduced motion.

### A short demo path

1. Sign in as **Maya Brooks**.
2. Open **Alignment check** and select **Practice a café opening routine**.
3. Run the check. The original activity numbers the steps for the learner (the local rule quotes **“1. Gather the cleaning supplies”**) even though the goal asks the learner to choose a plan. With AI on, the demand map shows planning and sequencing as **Done for the learner**.
4. Generate a revision and review the AI-suggested title, the task cards, and every approved accommodation.
5. Edit and save the draft. To demonstrate the guard, remove a listed accommodation from the content, save, and inspect the blocked explanation; restore it and save again.
6. Approve the revision and choose **Run a practice session**. Any older drafts are retired so they cannot be approved by mistake.
7. Turn on **Easier reading** and start the **Thinking time** timer (it marks the extra-time support as used). Arrange the cards in the order the learner chose, record their reasoning, prompting, and supports used, and save. No mastery score is produced.
8. Record a teacher observation, then open the activity history to inspect the decision trail.

### Seed data and reset

The backend automatically seeds its SQLite file on first startup with **30 goals, 30 activities, 30 revisions, 30 checks, 28 observations, 38 history entries, and 3 demo users**. The seed includes aligned, mismatched, and unclear checks; draft, blocked, rejected, and approved revisions; archived goals; overdue dates; long text; and an empty observation context. Seed dates are anchored to November 5, 2026 for a reproducible demo, and are moved earlier if a reset happens before then so new work always sorts first.

Use **Reset demo workspace** in the workspace controls and confirm the dialog to restore the seed. The authenticated **`POST /api/reset`** endpoint does the same. Reset discards changes made in this prototype and leaves the source seed unchanged.

SQLite state is stored at `backend/.data/strivetrack.sqlite3` by default. The app has no dependency on a database server.

Approved and rejected revisions are immutable decision records. Create a new revision when another version is needed. Deletion of a linked goal or activity returns **409 Conflict** to protect its relationships and history; archive the record instead. Draft revisions and teacher observations can be edited or deleted through their supported flows.

## Run each server manually

The combined startup command is recommended. These macOS/Linux commands are useful when running each server in a separate terminal.

Backend, from `prototype/`:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install --cache-dir .cache/pip -r requirements.txt
PYTHONPYCACHEPREFIX="$PWD/.cache/pycache" backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001 --reload
```

Frontend, in another terminal from `prototype/`:

```sh
cd frontend
npm install --cache ../.cache/npm --no-audit --no-fund
npm run dev
```

On Windows, use `backend\.venv\Scripts\python.exe` for the virtual environment executable. The `npm run setup` and `npm run dev` scripts select the correct executable automatically. Activate the virtual environment if you prefer calling `python` directly. Set optional environment variables using your shell's normal syntax.

Vite forwards `/api` requests to port **8001**, and its frontend port is fixed at **5173**. The launcher checks both ports before starting anything. It reuses healthy StriveTrack services and starts any missing service. If another application occupies either port, it reports that port without stopping the application. Reused servers stay under their original terminal; Ctrl+C only stops newly started servers. The combined launcher runs one backend process for clean shutdown; the manual backend command above adds optional automatic reload during development.

## Verification

From `prototype/` after setup:

```sh
npm run check
npm run test:backend
npm run test:launcher
```

`check` runs ESLint, TypeScript checks, and the production frontend build. Backend tests exercise authentication, CRUD and validation, relationships, pagination/filtering, evidence, accommodation guards, approval gating, and reset using an isolated temporary store.

For browser end-to-end checks, keep `npm run dev` running in another terminal. If Google Chrome is installed on macOS, run from `prototype/`:

```sh
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" npm run test:e2e
```

On other systems, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to the installed Chrome/Chromium executable. Alternatively, install a test browser inside the prototype, then run the suite (macOS/Linux):

```sh
cd frontend
PLAYWRIGHT_BROWSERS_PATH="$PWD/../.cache/ms-playwright" npx --cache ../.cache/npm playwright install chromium
cd ..
PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright" npm run test:e2e
```

Verified locally: **21 backend tests (including AI boundary tests with a mock model), lint, TypeScript, and production build pass**. The browser tests predate the session-record screen. All six workspace screens also fit at 320, 390, 768, and 1440 pixels without page overflow.

The browser installation is only needed for development tests. It is not needed to launch or click through the app in your normal browser.

## API and implementation

All business routes require the bearer token returned by `POST /api/auth/login`. `GET /api/health` and `GET /api/demo-users` are public. Open `/docs` to inspect request models and try individual operations.

| Routes | Purpose |
| --- | --- |
| `/api/auth/login`, `/api/auth/me` | Simulated login and current demo user |
| `/api/dashboard` | Summary, weekly chart, recent activities, and history |
| `/api/goals`, `/api/goals/{id}` | List, create, read, update, and delete goals |
| `/api/activities`, `/api/activities/{id}` | List, create, read, update, and delete activities |
| `/api/checks`, `/api/checks/{id}` | Run and inspect local alignment checks |
| `/api/revisions`, `/api/revisions/{id}` | Generate, inspect, edit, and delete eligible drafts |
| `/api/revisions/{id}/approve`, `/api/revisions/{id}/reject` | Teacher decisions with recorded history |
| `/api/observations`, `/api/observations/{id}` | Teacher observation CRUD |
| `/api/try/{activity_id}`, `/api/try/{activity_id}/submit` | Approved learner activity and practice submission |
| `/api/audit` | Read-only activity history |
| `/api/reset` | Restore all synthetic seed records |

Lists support search, filtering, sorting, and pagination where applicable. Responses use `{items, total, page, page_size, pages}`. Pydantic validates inputs; the API returns clear 401, 404, 409, and 422 responses and enables CORS for the local frontend.

```text
prototype/
  package.json          Setup, combined startup, and verification commands
  requirements.txt      Backend dependency entry point
  .env.example          Optional overrides; no secrets needed
  scripts/              Cross-platform local task runners
  frontend/             React, TypeScript, Vite, Tailwind, Framer Motion,
                        React Router, TanStack Query, Lucide, Sonner
  backend/              FastAPI, Pydantic, SQLite, pytest
  seed/                 Synthetic records loaded on first startup/reset
```

Typography is bundled locally through Fontsource Nunito. Avatars, gradients, clay surfaces, icons, and charts are rendered locally; no remote image or font service is required.

## Responsible AI

StriveTrack uses an OpenAI-compatible model (`qwen3-30b-a3b` on `https://openai.rc.asu.edu/v1`, set in `.env`; a check takes about 8 seconds) in two places, and wraps each one in rules enforced in code: **AI suggests, StriveTrack verifies, the teacher decides.**

| AI does | Code guarantees |
| --- | --- |
| Builds an executive-function demand map: for planning, sequencing, task initiation, working memory, self-monitoring, and flexible thinking, whether the goal targets it and whether the activity leaves it to the learner | Only those six skills and three answers are accepted; anything else is discarded. Without AI, local rules fill in planning and sequencing. |
| Reviews an activity against the goal and names skill bypasses with a quote | Each quote is matched against the activity text; any finding whose quote is not found is removed and the teacher is told. The local rules always run too. |
| Writes a revision: learner-friendly instructions, task cards with picture cues, a reflection question | Cards are shown in a different order than the AI wrote them. Approved accommodations are added word for word by code, not by the AI, and the approval guard still applies. |

- **Data sent:** only the goal text and the activity text. Learner codes, sessions, and observations are never sent.
- **Teacher in control:** nothing reaches a practice session until a teacher approves it, and every AI-assisted check and draft is labeled with the model name in the screen and the history.
- **Failure-safe:** if the key is missing or the model is unreachable, StriveTrack falls back to local rules and says so.

## Roadmap: from MVP to classrooms

This is an MVP. The path to real use is deliberate, and every step keeps the teacher as the decision-maker.

| Stage | What changes | Why it matters |
| --- | --- | --- |
| **1. Teacher pilot (one semester)** | 5–10 special-education teachers use StriveTrack with fictional or de-identified activities. We measure minutes saved per revision, how often teachers accept, edit, or reject AI suggestions, and how often a skill bypass was caught before practice. | Evidence that it saves time and improves fit, not a claim. |
| **2. Real sign-in and roles** | School single sign-on (Google or Microsoft), signed sessions, per-school data separation, and case-manager versus teacher permissions. | Replaces the demo sign-in; students never get accounts. |
| **3. Student-data privacy** | FERPA and state student-privacy agreements, a school-approved or self-hosted model so no text leaves the district, data retention limits, and learner codes mapped to students only inside the school's system. | Schools can adopt it without new privacy risk. |
| **4. IEP system integration** | Import goals and accommodations from IEP systems instead of retyping them; export session records and teacher observations as progress-monitoring evidence for the IEP team. | Fits existing paperwork instead of adding to it. |
| **5. Broader skills and languages** | Demand maps for more executive-function and transition skills, Spanish learner-facing cards, and picture-symbol card sets. | Reaches more learners and families. |

## Limits and attribution

The checker recognizes a limited set of activity patterns and is not a validated semantic or educational assessment, with or without AI. Teachers must review the content and accommodation choices. No real learner information belongs in this demo.

Authentication is intentionally simulated. This local prototype does not provide production security, school isolation, IEP system integrations, or a research-validated effectiveness claim. Browser speech support and available voices depend on the user's browser and operating system.

Implementation was created with AI coding assistance. The maintainers should review it and be able to explain its behavior before using it in a hackathon submission or extending it. The project builds on the open-source libraries named above; exact installed frontend versions are recorded in `frontend/package-lock.json`, and backend versions are pinned in `backend/requirements.txt`.

Everything for this standalone prototype lives within `prototype/`. The surrounding workspace is not a Git repository, so `git status` at the workspace root cannot report a diff; no parent repository was initialized or existing application files modified.

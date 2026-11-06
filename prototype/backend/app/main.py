"""StriveTrack demo API. Optional AI assistance; approval rules are always enforced locally."""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import sys
import threading
from contextlib import asynccontextmanager, contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator

PROTOTYPE_ROOT = Path(__file__).resolve().parents[2]
if str(PROTOTYPE_ROOT) not in sys.path:
    sys.path.insert(0, str(PROTOTYPE_ROOT))
from seed.data import build_seed  # noqa: E402
from app.ai import AIAssistant, normalize  # noqa: E402

DEMO_PASSWORD = "strivetrack-demo"
ENTITIES = ("users", "goals", "activities", "checks", "revisions", "observations", "sessions", "audit")


def rule_demand_map(goal: dict, content: str, preordered: bool, has_cards: bool) -> List[dict]:
    skill = goal["skill_description"]
    chooses = has_cards or bool(re.search(r"\b(choose|decide|your own plan|you pick)\b", content, re.I))
    demand = "done_for_learner" if preordered else "learner_does" if chooses else "not_required"
    rows = []
    for name, pattern in (("planning", r"plan|organi[sz]|choose\b.*\border"), ("sequencing", r"sequenc|order")):
        rows.append({"skill": name, "goal_targets": bool(re.search(pattern, skill, re.I)), "activity": demand, "note": "Numbered or pre-ordered steps." if preordered else "", "source": "rules"})
    return rows


def missing_supports(goal: dict, content: str, accommodations: List[str]) -> List[str]:
    text = normalize(content)
    listed = {normalize(item) for item in accommodations}
    return [support for support in goal["accommodations"] if normalize(support) not in text or normalize(support) not in listed]


def goal_fingerprint(goal: dict) -> str:
    parts = [goal["skill_description"], goal["success_criteria"]] + sorted(goal["accommodations"])
    return hashlib.sha256(normalize("\n".join(parts)).encode()).hexdigest()[:16]


def content_fingerprint(content: str) -> str:
    return hashlib.sha256(normalize(content).encode()).hexdigest()[:16]


def with_staleness(check: dict, goals: dict, activities: dict) -> dict:
    goal, activity = goals.get(check["goal_id"]), activities.get(check["activity_id"])
    reasons = []
    if goal and goal_fingerprint(goal) != check.get("goal_fingerprint", goal_fingerprint(goal)):
        reasons.append("goal")
    if activity and content_fingerprint(activity["content"]) != check.get("content_fingerprint", content_fingerprint(activity["content"])):
        reasons.append("activity")
    return dict(check, stale=bool(reasons), stale_reasons=reasons)


LOCK = threading.RLock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return prefix + "_" + uuid4().hex[:12]


class Store:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(str(self.path), timeout=15)
        connection.execute("PRAGMA busy_timeout = 15000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS records (entity TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(entity,id))")
            connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")
            seeded = connection.execute("SELECT value FROM metadata WHERE key='seeded'").fetchone()
        if not seeded:
            self.reset()

    def reset(self):
        import json
        seeded = build_seed()
        goals = {goal["id"]: goal for goal in seeded["goals"]}
        activities = {activity["id"]: activity for activity in seeded["activities"]}
        for check in seeded["checks"]:
            check.update(goal_fingerprint=goal_fingerprint(goals[check["goal_id"]]), content_fingerprint=content_fingerprint(activities[check["activity_id"]]["content"]))
        with LOCK, self.connect() as connection:
            connection.execute("DELETE FROM records")
            for entity, values in seeded.items():
                for value in values:
                    connection.execute("INSERT INTO records VALUES (?,?,?)", (entity, value["id"], json.dumps(value)))
            connection.execute("INSERT OR REPLACE INTO metadata VALUES ('seeded','1')")
        return {entity: len(values) for entity, values in seeded.items()}

    def all(self, entity: str) -> List[dict]:
        import json
        with self.connect() as connection:
            return [json.loads(row[0]) for row in connection.execute("SELECT data FROM records WHERE entity=?", (entity,))]

    def get(self, entity: str, identifier: str) -> dict:
        import json
        with self.connect() as connection:
            row = connection.execute("SELECT data FROM records WHERE entity=? AND id=?", (entity, identifier)).fetchone()
        if not row:
            raise HTTPException(404, entity.rstrip("s").capitalize() + " not found.")
        return json.loads(row[0])

    def put(self, entity: str, value: dict) -> dict:
        import json
        with self.connect() as connection:
            connection.execute("INSERT OR REPLACE INTO records VALUES (?,?,?)", (entity, value["id"], json.dumps(value)))
        return value

    def delete(self, entity: str, identifier: str):
        with self.connect() as connection:
            connection.execute("DELETE FROM records WHERE entity=? AND id=?", (entity, identifier))


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Input):
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=1, max_length=128)


class GoalCreate(Input):
    title: str = Field(min_length=3, max_length=140)
    skill_description: str = Field(min_length=10, max_length=5000)
    success_criteria: str = Field(min_length=5, max_length=2500)
    accommodations: List[str] = Field(default_factory=list, max_length=20)
    category: str = Field(default="Workplace", min_length=1, max_length=80)
    status: Literal["active", "archived"] = "active"
    due_date: date = Field(default_factory=lambda: date(2026, 11, 12))

    @field_validator("accommodations")
    @classmethod
    def valid_accommodations(cls, values):
        result = [value.strip() for value in values]
        if any(not value or len(value) > 500 for value in result):
            raise ValueError("Each accommodation must contain 1–500 characters.")
        if len(set(result)) != len(result):
            raise ValueError("Accommodations must be unique.")
        return result


class GoalPatch(Input):
    title: Optional[str] = Field(default=None, min_length=3, max_length=140)
    skill_description: Optional[str] = Field(default=None, min_length=10, max_length=5000)
    success_criteria: Optional[str] = Field(default=None, min_length=5, max_length=2500)
    accommodations: Optional[List[str]] = Field(default=None, max_length=20)
    category: Optional[str] = Field(default=None, min_length=1, max_length=80)
    status: Optional[Literal["active", "archived"]] = None
    due_date: Optional[date] = None

    @field_validator("accommodations")
    @classmethod
    def valid_accommodations(cls, values):
        return None if values is None else GoalCreate.valid_accommodations(values)


class ActivityCreate(Input):
    goal_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=3, max_length=140)
    content: str = Field(min_length=10, max_length=20000)
    category: str = Field(default="Workplace", min_length=1, max_length=80)
    status: Literal["draft", "needs_review", "approved", "archived"] = "draft"
    due_date: date = Field(default_factory=lambda: date(2026, 11, 12))
    color: Literal["peach", "mint", "lavender", "lemon"] = "lavender"


class ActivityPatch(Input):
    goal_id: Optional[str] = Field(default=None, min_length=1, max_length=100)
    title: Optional[str] = Field(default=None, min_length=3, max_length=140)
    content: Optional[str] = Field(default=None, min_length=10, max_length=20000)
    category: Optional[str] = Field(default=None, min_length=1, max_length=80)
    status: Optional[Literal["draft", "needs_review", "approved", "archived"]] = None
    due_date: Optional[date] = None
    color: Optional[Literal["peach", "mint", "lavender", "lemon"]] = None


class RevisionCreate(Input):
    activity_id: str = Field(min_length=1, max_length=100)
    content: Optional[str] = Field(default=None, min_length=10, max_length=20000)
    accommodations: Optional[List[str]] = Field(default=None, max_length=20)


class RevisionPatch(Input):
    content: Optional[str] = Field(default=None, min_length=10, max_length=20000)
    accommodations: Optional[List[str]] = Field(default=None, max_length=20)


class ObservationCreate(Input):
    activity_id: str = Field(min_length=1, max_length=100)
    note: str = Field(min_length=3, max_length=5000)
    context: str = Field(default="", max_length=1000)


class ObservationPatch(Input):
    note: Optional[str] = Field(default=None, min_length=3, max_length=5000)
    context: Optional[str] = Field(default=None, max_length=1000)


class CheckCreate(Input):
    activity_id: str = Field(min_length=1, max_length=100)


class Reject(Input):
    reason: str = Field(min_length=3, max_length=1500)


class SessionCreate(Input):
    ordered_steps: List[str] = Field(min_length=2, max_length=20)
    learner_label: str = Field(default="Learner", min_length=1, max_length=40)
    reasoning: str = Field(default="", max_length=2000)
    prompting: Literal["independent", "one_prompt", "several_prompts", "modeled"] = "independent"
    supports_used: List[str] = Field(default_factory=list, max_length=20)


def body_dict(body: Input) -> dict:
    return body.model_dump(mode="json", exclude_unset=True, exclude_none=True)


def paginated(values: List[dict], q="", status=None, category=None, goal_id=None, activity_id=None,
              sort="updated_at", order="desc", page=1, page_size=12) -> dict:
    if q:
        query = q.casefold().strip()
        values = [value for value in values if query in " ".join(str(value.get(key, "")) for key in ("title", "content", "skill_description", "success_criteria", "note", "context", "actor", "action", "target", "detail")).casefold()]
    for key, expected in (("status", status), ("category", category), ("goal_id", goal_id), ("activity_id", activity_id)):
        if expected and expected != "all":
            values = [value for value in values if value.get(key) == expected]
    values = sorted(values, key=lambda value: str(value.get(sort, value.get("created_at", ""))).casefold(), reverse=order == "desc")
    total = len(values)
    return {"items": values[(page - 1) * page_size:page * page_size], "total": total, "page": page, "page_size": page_size, "pages": (total + page_size - 1) // page_size}


def list_query(q: str = Query("", max_length=200), status: Optional[str] = Query(None, max_length=50),
               category: Optional[str] = Query(None, max_length=80), goal_id: Optional[str] = Query(None, max_length=100),
               activity_id: Optional[str] = Query(None, max_length=100),
               sort: Literal["updated_at", "title", "created_at", "due_date"] = "updated_at",
               order: Literal["asc", "desc"] = "desc", page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=100)):
    return dict(q=q, status=status, category=category, goal_id=goal_id, activity_id=activity_id, sort=sort, order=order, page=page, page_size=page_size)


security = HTTPBearer(auto_error=False)


def create_app(database_path: Optional[Path] = None, ai: Optional[AIAssistant] = None) -> FastAPI:
    store = Store(database_path or Path(os.environ.get("STRIVETRACK_DB", str(PROTOTYPE_ROOT / "backend" / ".data" / "strivetrack.sqlite3"))))
    ai = ai or AIAssistant.from_env(PROTOTYPE_ROOT / ".env")

    @asynccontextmanager
    async def lifespan(application):
        store.initialize()
        yield

    app = FastAPI(title="StriveTrack · Local Demo API", version="1.0.0", description="Synthetic data and simulated authentication. Alignment checks and revision drafts can use an optional AI model; quoted evidence is verified and approved accommodations are enforced in code. All teacher decisions are recorded; this tool never determines mastery.", lifespan=lifespan)
    app.state.store = store
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        errors = [{"field": ".".join(str(x) for x in item["loc"] if x != "body"), "message": item["msg"]} for item in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": "Please check the highlighted fields.", "errors": errors})

    def current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> dict:
        if not credentials or not credentials.credentials.startswith("demo-"):
            raise HTTPException(401, "Please sign in with a demo account.", headers={"WWW-Authenticate": "Bearer"})
        identifier = credentials.credentials[5:]
        try:
            return store.get("users", identifier)
        except HTTPException:
            raise HTTPException(401, "This demo session is no longer available. Please sign in again.")

    def audit(user: dict, action: str, target: dict, detail: str, version: Optional[int] = None):
        value = {"id": new_id("audit"), "actor": user["name"], "action": action, "target": target.get("title", "Activity revision"), "target_id": target["id"], "version": version, "created_at": now(), "detail": detail}
        store.put("audit", value)

    def mutable_revision(identifier: str) -> dict:
        revision = store.get("revisions", identifier)
        if revision["status"] == "superseded":
            raise HTTPException(409, "A newer version was approved after this draft. Create a new revision to make changes.")
        if revision["status"] in ("approved", "rejected"):
            raise HTTPException(409, "This decision is part of the approval history. Create a new revision to make changes.")
        return revision

    def check_accommodations(revision: dict, goal: dict) -> dict:
        missing = missing_supports(goal, revision["content"], revision["accommodations"])
        revision["status"] = "blocked" if missing else "draft"
        revision["blocked_reason"] = ("Restore the approved accommodation(s): " + "; ".join(missing)) if missing else None
        return revision

    def learner_payload(identifier: str) -> dict:
        activity = store.get("activities", identifier)
        if activity["status"] != "approved":
            raise HTTPException(409, "This activity needs teacher approval before a learner can open it.")
        approved = [r for r in store.all("revisions") if r["activity_id"] == identifier and r["status"] == "approved"]
        if not approved:
            raise HTTPException(409, "Approve a revision before opening learner practice.")
        revision = max(approved, key=lambda r: r["version"])
        goal = store.get("goals", activity["goal_id"])
        if goal["status"] == "archived":
            raise HTTPException(409, "This goal is archived. Restore it before learner practice.")
        if missing_supports(goal, revision["content"], revision["accommodations"]):
            raise HTTPException(409, "Approved accommodations have changed. Review and approve a new revision first.")
        supports = {normalize(s) for s in goal["accommodations"]}
        content = revision["content"]
        marker = re.search(r"(?:Step cards|Task cards|Your step cards):\s*\n", content, re.IGNORECASE)
        step_text = content[marker.end():] if marker else content
        steps = []
        for line in step_text.splitlines():
            clean = re.sub(r"^\s*(?:[-•*]|\d+[.)])\s*", "", line).strip()
            if not clean or clean.lower().startswith(("approved supports", "accommodations", "supports:", "reflection", "teacher")):
                if steps:
                    break
                continue
            if normalize(clean) in supports:
                continue
            if marker or re.match(r"^\s*[-•*\d]", line):
                steps.append(clean)
            if len(steps) == 6:
                break
        if len(steps) < 2:
            steps = ["Gather the materials you need.", "Complete the workplace task.", "Check your work and put materials away."]
        return {"activity": activity, "revision": revision, "goal": goal, "steps": steps}

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": "local-demo"}

    @app.get("/api/ai/status")
    def ai_status(user=Depends(current_user)):
        return ai.status()

    @app.get("/api/demo-users")
    def demo_users():
        return store.all("users")

    @app.post("/api/auth/login")
    def login(payload: Login):
        user = next((u for u in store.all("users") if u["email"].casefold() == payload.email.casefold()), None)
        if not user or payload.password != DEMO_PASSWORD:
            raise HTTPException(401, "The email or demo password is incorrect.")
        return {"token": "demo-" + user["id"], "user": user}

    @app.get("/api/auth/me")
    def me(user=Depends(current_user)):
        return user

    @app.post("/api/reset")
    def reset(user=Depends(current_user)):
        counts = store.reset()
        return {"message": "The demo has been restored to its original seed data.", "counts": counts}

    @app.get("/api/dashboard")
    def dashboard(user=Depends(current_user)):
        goals, activities = store.all("goals"), store.all("activities")
        revisions, checks, events = store.all("revisions"), store.all("checks"), store.all("audit")
        goal_map = {g["id"]: g for g in goals}
        latest = {}
        for r in revisions:
            if r["status"] == "approved" and r["version"] > latest.get(r["activity_id"], {"version": 0})["version"]:
                latest[r["activity_id"]] = r
        # Share of approved activities whose latest approved version still states every current goal support.
        kept = sum(not missing_supports(goal_map[r["goal_id"]], r["content"], r["accommodations"]) for r in latest.values() if r["goal_id"] in goal_map)
        preserved = round(100 * kept / len(latest)) if latest else 100
        # Seven days of real seeded check/approval timestamps, never fabricated counts.
        anchor = max([datetime.fromisoformat(c["created_at"].replace("Z", "+00:00")).date() for c in checks], default=datetime.now(timezone.utc).date())
        from datetime import timedelta
        weekly = []
        for offset in range(6, -1, -1):
            day = anchor - timedelta(days=offset)
            weekly.append({"label": day.strftime("%a"), "checked": sum(c["created_at"][:10] == day.isoformat() for c in checks), "approved": sum(r["status"] == "approved" and r.get("updated_at", r["created_at"])[:10] == day.isoformat() for r in revisions)})
        return {"stats": {"active_goals": sum(g["status"] == "active" for g in goals), "activities": len(activities), "needs_review": sum(a["status"] == "needs_review" for a in activities), "approved": sum(a["status"] == "approved" for a in activities), "accommodations_kept": preserved}, "weekly": weekly, "recent_activities": sorted(activities, key=lambda a: a["updated_at"], reverse=True)[:5], "recent_audit": sorted(events, key=lambda a: a["created_at"], reverse=True)[:5], "user": user}

    @app.get("/api/goals")
    def goals(query=Depends(list_query), user=Depends(current_user)):
        return paginated(store.all("goals"), **query)

    @app.get("/api/goals/{identifier}")
    def goal(identifier: str, user=Depends(current_user)):
        return store.get("goals", identifier)

    @app.post("/api/goals", status_code=201)
    def create_goal(payload: GoalCreate, user=Depends(current_user)):
        value = payload.model_dump(mode="json")
        value.update(id=new_id("goal"), created_at=now(), updated_at=now(), created_by=user["id"])
        store.put("goals", value)
        audit(user, "created", value, "Added an approved goal to the local library.")
        return value

    @app.patch("/api/goals/{identifier}")
    def update_goal(identifier: str, payload: GoalPatch, user=Depends(current_user)):
        with LOCK:
            value = store.get("goals", identifier)
            changes = body_dict(payload)
            supports_changed = "accommodations" in changes and set(changes["accommodations"]) != set(value["accommodations"])
            value.update(changes, updated_at=now())
            store.put("goals", value)
            # Form saves include unchanged supports. Only a changed support set
            # requires another teacher review before learner access.
            if supports_changed:
                for activity in store.all("activities"):
                    if activity["goal_id"] == identifier and activity["status"] == "approved":
                        activity.update(status="needs_review", updated_at=now())
                        store.put("activities", activity)
            audit(user, "updated", value, "Updated goal details; learner support changes require renewed approval.")
            return value

    @app.delete("/api/goals/{identifier}")
    def delete_goal(identifier: str, user=Depends(current_user)):
        with LOCK:
            value = store.get("goals", identifier)
            if any(a["goal_id"] == identifier for a in store.all("activities")):
                raise HTTPException(409, "This goal has linked activities. Archive it, or remove the linked activities first.")
            store.delete("goals", identifier)
            audit(user, "deleted", value, "Removed an unused goal.")
            return {"message": "Goal deleted."}

    @app.get("/api/activities")
    def activities(query=Depends(list_query), user=Depends(current_user)):
        return paginated(store.all("activities"), **query)

    @app.get("/api/activities/{identifier}")
    def activity(identifier: str, user=Depends(current_user)):
        return store.get("activities", identifier)

    @app.post("/api/activities", status_code=201)
    def create_activity(payload: ActivityCreate, user=Depends(current_user)):
        store.get("goals", payload.goal_id)
        if payload.status == "approved":
            raise HTTPException(409, "Save the activity as a draft, then review and approve a revision.")
        value = payload.model_dump(mode="json")
        value.update(id=new_id("activity"), created_at=now(), updated_at=now(), created_by=user["id"])
        store.put("activities", value)
        audit(user, "created", value, "Created a new activity draft.")
        return value

    @app.patch("/api/activities/{identifier}")
    def update_activity(identifier: str, payload: ActivityPatch, user=Depends(current_user)):
        with LOCK:
            value = store.get("activities", identifier)
            changes = body_dict(payload)
            if "goal_id" in changes:
                store.get("goals", changes["goal_id"])
                if changes["goal_id"] != value["goal_id"] and any(r["activity_id"] == identifier for r in store.all("revisions")):
                    raise HTTPException(409, "This activity has revision history. Create a new activity to use a different goal.")
            if changes.get("status") == "approved" and value["status"] != "approved":
                raise HTTPException(409, "Approve a revision to make this activity available to learners.")
            if "content" in changes and changes["content"] != value["content"] and value["status"] == "approved":
                changes["status"] = "needs_review"
            value.update(changes, updated_at=now())
            store.put("activities", value)
            audit(user, "updated", value, "Updated activity details.")
            return value

    @app.delete("/api/activities/{identifier}")
    def delete_activity(identifier: str, user=Depends(current_user)):
        with LOCK:
            value = store.get("activities", identifier)
            if any(r["activity_id"] == identifier and r["status"] in ("approved", "rejected") for r in store.all("revisions")):
                raise HTTPException(409, "This activity has a recorded teacher decision. Archive it to preserve its history.")
            for entity in ("revisions", "checks", "observations"):
                for linked in store.all(entity):
                    if linked["activity_id"] == identifier:
                        store.delete(entity, linked["id"])
            store.delete("activities", identifier)
            audit(user, "deleted", value, "Deleted a draft activity and its unapproved working records.")
            return {"message": "Activity deleted."}

    def lookup_maps():
        return {g["id"]: g for g in store.all("goals")}, {a["id"]: a for a in store.all("activities")}

    @app.get("/api/checks")
    def checks(query=Depends(list_query), user=Depends(current_user)):
        result = paginated(store.all("checks"), **query)
        goals, activities = lookup_maps()
        result["items"] = [with_staleness(item, goals, activities) for item in result["items"]]
        return result

    @app.get("/api/checks/{identifier}")
    def check(identifier: str, user=Depends(current_user)):
        return with_staleness(store.get("checks", identifier), *lookup_maps())

    @app.post("/api/checks", status_code=201)
    def create_check(payload: CheckCreate, user=Depends(current_user)):
        activity = store.get("activities", payload.activity_id)
        goal = store.get("goals", activity["goal_id"])
        if activity["status"] == "archived" or goal["status"] == "archived":
            raise HTTPException(409, "Restore the archived activity and goal before running a check.")
        ai_review = ai.check(goal, activity["content"])
        with LOCK:
            activity = store.get("activities", payload.activity_id)
            content = activity["content"]
            findings = []
            numbered = re.search(r"(?m)^\s*1[.)]\s+[^\n]+", content)
            preordered = next((phrase for phrase in ("in this order", "in the correct order", "Follow these steps", "follow these steps", "already numbered") if phrase in content), None)
            planning = bool(re.search(r"plan|sequenc|order|organis|organiz", goal["skill_description"], re.I))
            if planning and (numbered or preordered):
                evidence = numbered.group(0).strip() if numbered else preordered
                findings.append({"type": "Skill bypass", "explanation": "The goal asks the learner to plan the order. This activity provides an order in advance, so it may practice following directions instead of planning. Offer unnumbered task cards and ask the learner to explain their sequence.", "evidence": evidence, "confidence": 0.96, "source": "rules"})
            for support in goal["accommodations"]:
                if normalize(support) not in normalize(content):
                    # Missing text cannot itself be quoted: use actual worksheet instruction as evidence.
                    quote = next((line.strip() for line in content.splitlines() if line.strip()), content[:120])
                    findings.append({"type": "Support not stated", "explanation": 'The approved support “' + support + '” is not stated in this activity. Confirm that it will be provided; StriveTrack cannot infer classroom supports.', "evidence": quote, "confidence": 0.81, "source": "rules"})
            findings = [finding for finding in findings if finding["evidence"] in content]
            has_task_detail = numbered or re.search(r"(?:step|task) cards:", content, re.I)
            unclear = len(content.split()) < 12 or (not has_task_detail and len(content.split()) < 40)
            if unclear:
                findings = []
            ai_note = None
            ai_used = bool(ai_review) and ai_review["content"] == content
            if ai_used:
                seen = {(f["type"].casefold(), f["evidence"]) for f in findings}
                for finding in ai_review["findings"]:
                    label = finding["type"].casefold()
                    if (label, finding["evidence"]) in seen or "support" in label or "accommodation" in label:
                        continue
                    findings.append(finding)
                if ai_review["dropped"]:
                    ai_note = "{} AI suggestion{} removed because the quoted text could not be found in the activity.".format(ai_review["dropped"], " was" if ai_review["dropped"] == 1 else "s were")
            elif ai.enabled:
                ai_note = "The AI model did not respond, so only the local rules were used."
            if findings:
                result = "mismatch"
            elif unclear and (not ai_used or ai_review["result"] == "unsure"):
                result = "unsure"
            else:
                result = "aligned"
            rule_summary = {"unsure": "There is not enough activity detail to check the planning demand. Add the instructions and available supports.", "mismatch": "This activity may do part of the planning for the learner. Review the quoted instructions and keep every approved support.", "aligned": "No obvious skill bypass was found. A teacher should still review the task and all supports before approval."}[result]
            summary = ai_review["summary"] if ai_used and ai_review["result"] == result and ai_review["summary"] else rule_summary
            demand_map = ai_review["demand_map"] if ai_used and ai_review["demand_map"] else rule_demand_map(goal, content, bool(numbered or preordered), bool(has_task_detail))
            value = {"id": new_id("check"), "activity_id": activity["id"], "goal_id": goal["id"], "result": result, "summary": summary, "findings": findings, "demand_map": demand_map, "created_at": now(), "updated_at": now(), "mode": "ai-assisted" if ai_used else "deterministic-demo", "ai_model": ai.model if ai_used else None, "ai_note": ai_note,
                     "goal_fingerprint": goal_fingerprint(goal), "content_fingerprint": content_fingerprint(content)}
            store.put("checks", value)
            if activity["status"] != "approved":
                activity.update(status="needs_review", updated_at=now())
                store.put("activities", activity)
            audit(user, "checked", activity, ("Ran an AI-assisted alignment check (" + ai.model + "): " if ai_used else "Ran the local alignment rules: ") + result + ".")
            return dict(value, stale=False, stale_reasons=[])

    @app.get("/api/revisions")
    def revisions(query=Depends(list_query), user=Depends(current_user)):
        return paginated(store.all("revisions"), **query)

    @app.get("/api/revisions/{identifier}")
    def revision(identifier: str, user=Depends(current_user)):
        return store.get("revisions", identifier)

    @app.post("/api/revisions", status_code=201)
    def create_revision(payload: RevisionCreate, user=Depends(current_user)):
        activity = store.get("activities", payload.activity_id)
        goal = store.get("goals", activity["goal_id"])
        if activity["status"] == "archived" or goal["status"] == "archived":
            raise HTTPException(409, "Restore the archived goal and activity before drafting a revision.")
        ai_draft = ai.revise(goal, activity) if payload.content is None else None
        with LOCK:
            goal = store.get("goals", activity["goal_id"])
            supports_text = "\n\nApproved supports:\n" + "\n".join("• " + support for support in goal["accommodations"])
            steps = [re.sub(r"^\s*\d+[.)]\s*", "", line).strip() for line in activity["content"].splitlines() if re.match(r"^\s*\d+[.)]\s*", line)]
            if len(steps) < 3:
                # Existing aligned worksheets already have unnumbered cards: preserve
                # their task content when adding or changing approved supports.
                card_section = re.search(r"(?:Step cards|Task cards|Your step cards):\s*\n(.*?)(?:\n\s*(?:Approved supports|Accommodations|Supports|Reflection):|\Z)", activity["content"], re.I | re.S)
                if card_section:
                    cards_from_source = [re.sub(r"^\s*[-•*]\s*", "", line).strip() for line in card_section.group(1).splitlines() if line.strip()]
                    if len(cards_from_source) >= 3:
                        steps = cards_from_source
            if len(steps) < 3:
                steps = ["Gather the materials for " + activity["title"].lower() + ".", "Complete the main task and check the result.", "Put materials away and tell your teacher how your plan worked."]
            steps = steps[:3]
            # Deterministically shuffle task cards; no 'correct' order is presented or scored.
            cards = [steps[1], steps[2], steps[0]]
            content = payload.content or (activity["title"] + "\n\nYour task: make your own plan for this routine. Choose what to do first, next, and last. Explain why your order works, then try it. You can change your plan.\n\nStep cards:\n" + "\n".join("• " + step for step in cards) + supports_text + "\n\nReflection: What helped you choose your order? What would you change next time?")
            if ai_draft:
                # Rotate the model's cards so they are never shown in the order it wrote them.
                ai_cards = ai_draft["cards"][1:] + ai_draft["cards"][:1]
                content = ai_draft["title"] + "\n\n" + ai_draft["instructions"] + "\n\nStep cards:\n" + "\n".join("• " + card for card in ai_cards) + supports_text + ("\n\nReflection: " + ai_draft["reflection"] if ai_draft["reflection"] else "")
            versions = [r["version"] for r in store.all("revisions") if r["activity_id"] == activity["id"]]
            value = {"id": new_id("revision"), "activity_id": activity["id"], "goal_id": goal["id"], "content": content, "accommodations": payload.accommodations if payload.accommodations is not None else goal["accommodations"].copy(), "status": "draft", "version": max(versions, default=0) + 1, "blocked_reason": None, "created_by": user["id"], "created_at": now(), "updated_at": now(),
                     "mode": "ai-assisted" if ai_draft else "deterministic-demo", "ai_model": ai.model if ai_draft else None, "ai_rationale": ai_draft["rationale"] if ai_draft else None,
                     "ai_note": "The AI model did not respond, so the local template was used." if ai.enabled and payload.content is None and not ai_draft else None}
            check_accommodations(value, goal)
            store.put("revisions", value)
            audit(user, "drafted", activity, ("Created an AI-assisted revision (" + ai.model + "); " if ai_draft else "Created a revision from the local template; ") + "every approved support is checked in code.", value["version"])
            return value

    @app.patch("/api/revisions/{identifier}")
    def update_revision(identifier: str, payload: RevisionPatch, user=Depends(current_user)):
        with LOCK:
            value = mutable_revision(identifier)
            value.update(body_dict(payload), updated_at=now())
            goal = store.get("goals", value["goal_id"])
            check_accommodations(value, goal)
            store.put("revisions", value)
            activity = store.get("activities", value["activity_id"])
            audit(user, "edited draft", activity, "Saved teacher edits to the draft. " + (value["blocked_reason"] + "." if value["status"] == "blocked" else "All approved supports are present."), value["version"])
            return value

    @app.delete("/api/revisions/{identifier}")
    def delete_revision(identifier: str, user=Depends(current_user)):
        with LOCK:
            value = mutable_revision(identifier)
            activity = store.get("activities", value["activity_id"])
            store.delete("revisions", identifier)
            audit(user, "deleted draft", activity, "Removed an unapproved revision.", value["version"])
            return {"message": "Draft revision deleted."}

    @app.post("/api/revisions/{identifier}/approve")
    def approve(identifier: str, user=Depends(current_user)):
        with LOCK:
            value = mutable_revision(identifier)
            goal = store.get("goals", value["goal_id"])
            activity = store.get("activities", value["activity_id"])
            if goal["status"] == "archived" or activity["status"] == "archived":
                raise HTTPException(409, "Restore the goal and activity before approving a revision.")
            check_accommodations(value, goal)
            if value["status"] == "blocked":
                store.put("revisions", value)
                raise HTTPException(409, value["blocked_reason"])
            value.update(status="approved", updated_at=now())
            activity.update(status="approved", updated_at=now())
            store.put("revisions", value)
            store.put("activities", activity)
            older = [r for r in store.all("revisions") if r["activity_id"] == activity["id"] and r["version"] < value["version"] and r["status"] in ("draft", "blocked")]
            for draft in older:
                draft.update(status="superseded", superseded_by=value["version"], updated_at=now())
                store.put("revisions", draft)
            one = len(older) == 1
            note = " Older draft{} {} {} retired so {} cannot be approved by mistake.".format("" if one else "s", ", ".join("v" + str(r["version"]) for r in older), "was" if one else "were", "it" if one else "they") if older else ""
            audit(user, "approved", activity, "Teacher approved this version for learner practice. All approved accommodations retained." + note, value["version"])
            return value

    @app.post("/api/revisions/{identifier}/reject")
    def reject(identifier: str, payload: Reject, user=Depends(current_user)):
        with LOCK:
            value = mutable_revision(identifier)
            value.update(status="rejected", rejection_reason=payload.reason, updated_at=now())
            activity = store.get("activities", value["activity_id"])
            store.put("revisions", value)
            audit(user, "rejected", activity, payload.reason, value["version"])
            return value

    @app.get("/api/observations")
    def observations(query=Depends(list_query), user=Depends(current_user)):
        return paginated(store.all("observations"), **query)

    @app.get("/api/observations/{identifier}")
    def observation(identifier: str, user=Depends(current_user)):
        return store.get("observations", identifier)

    @app.post("/api/observations", status_code=201)
    def create_observation(payload: ObservationCreate, user=Depends(current_user)):
        activity = store.get("activities", payload.activity_id)
        value = payload.model_dump(mode="json")
        value.update(id=new_id("observation"), created_at=now(), updated_at=now(), created_by=user["id"])
        store.put("observations", value)
        audit(user, "observed", activity, "Saved a teacher observation separately from the alignment check.")
        return value

    @app.patch("/api/observations/{identifier}")
    def update_observation(identifier: str, payload: ObservationPatch, user=Depends(current_user)):
        value = store.get("observations", identifier)
        value.update(body_dict(payload), updated_at=now())
        store.put("observations", value)
        audit(user, "edited observation", store.get("activities", value["activity_id"]), "Edited a teacher observation.")
        return value

    @app.delete("/api/observations/{identifier}")
    def delete_observation(identifier: str, user=Depends(current_user)):
        value = store.get("observations", identifier)
        store.delete("observations", identifier)
        audit(user, "deleted observation", store.get("activities", value["activity_id"]), "Deleted a teacher observation: “" + value["note"][:80] + ("…" if len(value["note"]) > 80 else "") + "”")
        return {"message": "Observation deleted."}

    @app.get("/api/try/{identifier}")
    def try_activity(identifier: str, user=Depends(current_user)):
        return learner_payload(identifier)

    @app.post("/api/try/{identifier}/submit", status_code=201)
    def submit_try(identifier: str, payload: SessionCreate, user=Depends(current_user)):
        value = learner_payload(identifier)
        if sorted(payload.ordered_steps) != sorted(value["steps"]):
            raise HTTPException(422, "Include every task card exactly once in the learner's order.")
        approved = {normalize(s): s for s in value["goal"]["accommodations"]}
        if any(normalize(s) not in approved for s in payload.supports_used):
            raise HTTPException(422, "Supports used must come from the approved accommodations.")
        session = {"id": new_id("session"), "activity_id": identifier, "revision_id": value["revision"]["id"], "version": value["revision"]["version"],
                   "learner_label": payload.learner_label, "ordered_steps": payload.ordered_steps, "reasoning": payload.reasoning, "prompting": payload.prompting,
                   "supports_used": [approved[normalize(s)] for s in payload.supports_used], "created_by": user["id"], "recorded_by": user["name"], "created_at": now(), "updated_at": now()}
        store.put("sessions", session)
        detail = "Recorded a practice session for " + payload.learner_label + ": " + " → ".join(payload.ordered_steps) + "." + (" Reasoning noted." if payload.reasoning else " No reasoning recorded.") + " No mastery judgment was made."
        audit(user, "session recorded", value["activity"], detail, value["revision"]["version"])
        return {"message": "Practice session saved.", "ordered_steps": payload.ordered_steps, "submitted_at": session["created_at"], "session": session}

    @app.get("/api/sessions")
    def sessions(query=Depends(list_query), user=Depends(current_user)):
        return paginated(store.all("sessions"), **query)

    @app.get("/api/audit")
    def audit_log(query=Depends(list_query), user=Depends(current_user)):
        return paginated(store.all("audit"), **query)

    return app


app = create_app()

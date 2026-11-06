"""Optional AI assistance through an OpenAI-compatible chat completions endpoint.

Every function here returns None when AI is not configured or the call fails,
so callers always fall back to the local rules. The model only ever receives
goal and activity text; observations, sessions and learner labels are never sent.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import List, Optional

import httpx

DEFAULT_BASE_URL = "https://openai.rc.asu.edu/v1"
DEFAULT_MODEL = "qwen3-30b-a3b"


def load_env_file(path: Path) -> None:
    """Read KEY=VALUE lines into os.environ without overriding the shell."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def locate_quote(content: str, quote: str) -> Optional[str]:
    """Return the exact passage of content matching quote, ignoring case and spacing."""
    words = quote.strip().strip("\"“”'").split()
    if len(words) < 2:
        return None
    match = re.search(r"\s+".join(re.escape(word) for word in words), content, re.IGNORECASE)
    return match.group(0) if match else None


def _parse_json(text: str) -> Optional[dict]:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


CHECK_SYSTEM = """You help special-education teachers check whether a practice activity lets a learner practice the skill named in their approved goal.
Many goals target executive-function skills: planning, sequencing, organizing, task initiation, self-monitoring, flexible thinking, and working memory.
An activity "bypasses" a skill when it does that thinking for the learner, for example:
- the goal asks the learner to plan or sequence, but the steps are already numbered or ordered;
- the goal asks the learner to choose, but the choice is made or reduced to one option;
- the goal asks the learner to self-check, but the answers or a completed example are given;
- the instructions pack many steps into one sentence, overloading working memory when that is not the skill being practiced.
Accommodations are checked separately by the teacher's software; do not report them.
Rules:
- Every finding needs "evidence": a short passage copied word for word from the ACTIVITY text. Never paraphrase it.
- Do not diagnose, label, or judge the learner. Write plainly for a busy teacher.
- At most 4 findings. If the activity text is too short to judge, use result "unsure".
Also build a demand map for these executive-function skills: planning, sequencing, task_initiation, working_memory, self_monitoring, flexible_thinking.
For each skill say whether the GOAL targets it, and what the ACTIVITY does with it:
"learner_does" (the learner must use the skill), "done_for_learner" (the activity does that thinking for them), or "not_required".
Reply with JSON only:
{"result": "aligned" | "mismatch" | "unsure", "summary": "one or two sentences", "findings": [{"type": "short label", "explanation": "why it matters and what to change", "evidence": "exact quote"}],
 "demand_map": [{"skill": "planning", "goal_targets": true, "activity": "done_for_learner", "note": "under 15 words"}]}"""

EF_SKILLS = ("planning", "sequencing", "task_initiation", "working_memory", "self_monitoring", "flexible_thinking")
EF_DEMANDS = ("learner_does", "done_for_learner", "not_required")


def clean_demand_map(raw) -> List[dict]:
    rows = {}
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        skill = str(item.get("skill", "")).strip().lower().replace(" ", "_").replace("-", "_")
        demand = str(item.get("activity", "")).strip().lower()
        if skill in EF_SKILLS and demand in EF_DEMANDS and skill not in rows:
            rows[skill] = {"skill": skill, "goal_targets": item.get("goal_targets") is True, "activity": demand, "note": str(item.get("note", "")).strip()[:140], "source": "ai"}
    return [rows[skill] for skill in EF_SKILLS if skill in rows]

REVISION_SYSTEM = """You help special-education teachers revise a practice activity so the learner practices the skill in their approved goal, especially executive-function skills such as planning and sequencing.
Write for the learner: short sentences, everyday words, about a grade 3 reading level, encouraging and never judgmental.
Keep the same real-world task, setting, and materials as the original activity.
Do not number the task cards or present them in the order they should be done; the learner decides the order.
Start each task card with one emoji that pictures the action, so the cards work as visual cues.
Do not list or rewrite the accommodations; the teacher's approved supports are added separately.
Give the activity a new title that names the task and invites planning; do not reuse wording from the original title that gives the plan away (for example "copy" or "follow").
Reply with JSON only:
{"title": "a learner-facing title under 8 words", "instructions": "2-4 sentences telling the learner to choose and explain their own order", "task_cards": ["3 to 5 cards, one action each, under 12 words"], "reflection": "one or two questions about how their plan worked", "rationale": "one or two sentences for the teacher explaining what changed and why"}"""


class AIAssistant:
    def __init__(self, api_key: str = "", base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL, timeout: float = 60.0, transport: Optional[httpx.BaseTransport] = None):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.transport = transport

    @classmethod
    def from_env(cls, env_file: Optional[Path] = None) -> "AIAssistant":
        if env_file:
            load_env_file(env_file)
        return cls(
            api_key=os.environ.get("STRIVETRACK_AI_API_KEY", ""),
            base_url=os.environ.get("STRIVETRACK_AI_BASE_URL", "") or DEFAULT_BASE_URL,
            model=os.environ.get("STRIVETRACK_AI_MODEL", "") or DEFAULT_MODEL,
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def status(self) -> dict:
        return {"enabled": self.enabled, "model": self.model if self.enabled else None}

    def _chat(self, system: str, user: str) -> Optional[dict]:
        if not self.enabled:
            return None
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.post(
                    self.base_url + "/chat/completions",
                    headers={"Authorization": "Bearer " + self.api_key},
                    json={"model": self.model, "temperature": 0.2, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"] or ""
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            return None
        return _parse_json(content)

    def check(self, goal: dict, content: str) -> Optional[dict]:
        prompt = "GOAL SKILL:\n{skill}\n\nSUCCESS CRITERIA:\n{criteria}\n\nAPPROVED ACCOMMODATIONS:\n{supports}\n\nACTIVITY:\n{content}".format(
            skill=goal["skill_description"], criteria=goal["success_criteria"],
            supports="\n".join("- " + s for s in goal["accommodations"]) or "(none)", content=content)
        value = self._chat(CHECK_SYSTEM, prompt)
        if not value or value.get("result") not in ("aligned", "mismatch", "unsure"):
            return None
        findings: List[dict] = []
        dropped = 0
        for item in value.get("findings") or []:
            if not isinstance(item, dict):
                continue
            evidence = locate_quote(content, str(item.get("evidence", "")))
            if not evidence:
                dropped += 1
                continue
            findings.append({"type": str(item.get("type") or "AI finding")[:60], "explanation": str(item.get("explanation", ""))[:600], "evidence": evidence, "confidence": 0.7, "source": "ai"})
        return {"result": value["result"], "summary": str(value.get("summary", ""))[:500], "findings": findings[:4], "dropped": dropped, "content": content, "demand_map": clean_demand_map(value.get("demand_map"))}

    def revise(self, goal: dict, activity: dict) -> Optional[dict]:
        prompt = "GOAL SKILL:\n{skill}\n\nSUCCESS CRITERIA:\n{criteria}\n\nORIGINAL ACTIVITY TITLE:\n{title}\n\nORIGINAL ACTIVITY:\n{content}".format(
            skill=goal["skill_description"], criteria=goal["success_criteria"], title=activity["title"], content=activity["content"])
        value = self._chat(REVISION_SYSTEM, prompt)
        if not value:
            return None
        cards = [re.sub(r"^\s*(?:[-•*]|\d+[.)])\s*", "", str(card)).strip()[:160] for card in value.get("task_cards") or []]
        cards = [card for card in cards if card]
        if not 3 <= len(cards) <= 6 or len(set(cards)) != len(cards):
            return None
        instructions = str(value.get("instructions", "")).strip()[:800]
        reflection = str(value.get("reflection", "")).strip()[:400]
        if not instructions:
            return None
        title = " ".join(str(value.get("title", "")).split())[:80]
        return {"title": title or activity["title"], "instructions": instructions, "cards": cards, "reflection": reflection, "rationale": str(value.get("rationale", "")).strip()[:500]}

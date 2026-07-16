"""
LLM utilities. Uses OpenAI if OPENAI_API_KEY is set; otherwise falls
back to deterministic templates so the app works fully offline.
"""

from __future__ import annotations

import json
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from openai import OpenAI
    _HAS_OPENAI = True
except Exception:
    _HAS_OPENAI = False


_MODEL = "gpt-4o-mini"  # Inexpensive default; override via OPENAI_MODEL.


def _client():
    if not _HAS_OPENAI:
        return None
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    return OpenAI()


def _summary_for_prompt(plan: dict) -> dict:
    """Slim down the plan dict for inclusion in a prompt."""
    return {
        "role": plan["role"],
        "target_headcount": plan["target_headcount"],
        "confirmed_count": len(plan["confirmed"]),
        "in_role_count": len(plan["in_role_confirmed"]),
        "movable_count": len(plan["movable_confirmed"]),
        "needs_verification_count": len(plan["needs_verification"]),
        "one_course_away_count": len(plan["one_course_away"]),
        "attrition": plan["attrition"],
        "hire_gap": plan["hire_gap"],
        "plan_cost": plan["plan_cost"],
        "hire_all_cost": plan["hire_all_cost"],
        "savings": plan["savings"],
        "savings_percent": plan["savings_percent"],
        "over_budget": plan["over_budget"],
        "data_quality": plan["data_quality"],
    }


def _chat(prompt: str) -> str | None:
    client = _client()
    if client is None:
        return None
    try:
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", _MODEL),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=400,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return None


# ----- Public API ------------------------------------------------------------

def generate_headline(plan_summary: dict, year: str = "2027 Q4") -> dict:
    """Return a structured headline: thesis (one sentence) + supporting line.

    The thesis is the single most important fact; the support sentence
    sets up deadline tension and the savings frame.
    """
    summary = _summary_for_prompt(plan_summary)
    prompt = (
        "You are a workforce planning advisor. Return JSON with two keys: "
        "'thesis' (one sentence under 16 words naming the gap and timeline) "
        "and 'support' (one sentence under 24 words naming the planned "
        "actions and how they compare to hiring everyone). Be direct, "
        "no preamble, no markdown. "
        f"Year target: {year}. Plan data: {json.dumps(summary)}"
    )
    out = _chat(prompt)
    if out:
        try:
            data = json.loads(out)
            if "thesis" in data and "support" in data:
                return data
        except (json.JSONDecodeError, TypeError):
            pass

    role = summary["role"]
    target = summary["target_headcount"]
    movable = summary["movable_count"]
    develop = summary["one_course_away_count"]
    gap = summary["hire_gap"]
    confirmed = summary["confirmed_count"]
    hire_all = summary["hire_all_cost"]
    plan_cost = summary["plan_cost"]

    thesis = (
        f"Only {confirmed} of {target} needed {role}s "
        f"are confirmed ready today."
    )
    support = (
        f"Plan: move {movable}, reskill {develop}, hire {gap} by {year} "
        f"for ${plan_cost / 1e6:.1f}M. "
        f"Hiring all {target} externally costs ${hire_all / 1e6:.1f}M "
        f"and takes 6 months."
    )
    return {"thesis": thesis, "support": support}


def generate_risk(plan_summary: dict) -> str:
    summary = _summary_for_prompt(plan_summary)
    prompt = (
        "Write 2 sentences on the key risks in this plan. Mention attrition "
        "uncertainty and data quality. Plan: " + json.dumps(summary)
    )
    out = _chat(prompt)
    if out:
        return out

    pct = summary["data_quality"]["pct_self_declared"]
    return (
        "Attrition is modeled per-employee from flight-risk scores. "
        "If retention worsens, the hire gap grows. "
        f"{pct}% of skill records are self-declared or inferred and "
        "may not reflect real capability."
    )


def chat_response(query: str, plan_summary: dict, lookup: dict | None = None) -> str:
    """Answer a chat question about the plan.

    `lookup` is an optional id -> {name, job_title, department} mapping
    used for the rule-based fallback when the LLM is unavailable.
    """
    summary = _summary_for_prompt(plan_summary)

    # Try LLM first.
    client = _client()
    if client is not None:
        prompt = (
            "You are a workforce planning advisor answering a question about "
            "this plan. Be concise (4 sentences max). Use the data; do not "
            "invent numbers.\n"
            f"Plan: {json.dumps(summary)}\n"
            f"Question: {query}"
        )
        out = _chat(prompt)
        if out:
            return out

    # Rule-based fallback.
    q = query.lower()
    lookup = lookup or {}

    def _names(ids: list, k: int = 5) -> str:
        rows = [lookup.get(i) for i in ids[:k]]
        rows = [r for r in rows if r]
        if not rows:
            return "no employees in this list."
        bullets = "\n".join(
            f"- {r['name']}, {r['job_title']} ({r['department']})"
            for r in rows
        )
        more = len(ids) - len(rows)
        suffix = f"\n...and {more} more." if more > 0 else ""
        return bullets + suffix

    if "move" in q or "movable" in q:
        return (
            f"{summary['movable_count']} confirmed people sit in other teams "
            f"and can be moved into the {summary['role']} role:\n"
            + _names(plan_summary["movable_confirmed"])
        )
    if "verify" in q or "verification" in q:
        return (
            f"{summary['needs_verification_count']} people match on paper but "
            "need a manager to confirm their skills:\n"
            + _names(plan_summary["needs_verification"])
        )
    if "course" in q or "reskill" in q or "develop" in q:
        return (
            f"{summary['one_course_away_count']} people are one course away. "
            "Each is missing exactly one required skill; everything else is "
            "trusted at proficiency 3+:\n"
            + _names(plan_summary["one_course_away"])
        )
    if "what if budget" in q or "what if target" in q or "rerun" in q or "re-run" in q:
        return "Use the controls at the top of the page to re-run the plan with new values."
    if "explain confirmed" in q or "what is confirmed" in q or "confirmed" in q:
        return (
            "Confirmed = employees with every required skill at proficiency 3+ "
            "and verified by a manager (within 6 months) or a course "
            "(within 2 years)."
        )
    if "attrition" in q or "flight" in q:
        return (
            f"Attrition estimate is {summary['attrition']} of "
            f"{summary['confirmed_count']} confirmed people, computed by "
            "summing per-employee flight-risk (default 15% when unknown)."
        )
    if "savings" in q or "save" in q or "cost" in q:
        return (
            f"Plan cost ${summary['plan_cost']/1e6:.1f}M vs. hire-all baseline "
            f"${summary['hire_all_cost']/1e6:.1f}M. Savings "
            f"${summary['savings']/1e6:.1f}M ({summary['savings_percent']}%)."
        )
    return (
        "I can answer about: who is movable, who needs verification, who is "
        "one course away, how attrition was estimated, and how the savings "
        "number is computed. Try one of those."
    )

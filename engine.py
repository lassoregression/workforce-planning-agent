"""
Core planning engine. Deterministic, no LLM.

Loads the mock workforce data, buckets employees against role
requirements, and produces a fully numeric plan summary the UI
can render directly.
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd

# ----- Configuration ---------------------------------------------------------

REQUIRED_SKILLS = {
    "AI Engineer": ["Python", "MLOps", "LLM Integration", "System Design"],
    "Data Engineer": ["Python", "SQL", "Spark", "ETL"],
    "Platform Engineer": ["Kubernetes", "Terraform", "CI/CD", "System Design"],
    "Backend Engineer": ["Java", "Spring", "System Design", "SQL"],
    "Legacy System Admin": ["COBOL", "JCL", "Mainframe", "Batch Processing"],
}

COURSE_NAMES = {
    "AI Engineer": "Advanced MLOps",
    "Data Engineer": "Spark for Data Engineers",
    "Platform Engineer": "Advanced Kubernetes",
    "Backend Engineer": "Cloud Native Java",
    "Legacy System Admin": "Mainframe Modernization",
}

MOVE_COST = 6_000
RESKILL_COST = 8_000
HIRE_COST = 45_000
VERIFY_COST = 0
DEFAULT_FLIGHT_RISK = 0.15
CURRENT_DATE = "2026-06-20"

DATA_PATH = Path(__file__).parent / "workforce_data.json"


# ----- Data loading ----------------------------------------------------------

def load_data() -> pd.DataFrame:
    """Load workforce data into a DataFrame.

    Falls back to a clear error if the file is missing. generate_data.py
    must be run first.
    """
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"{DATA_PATH.name} not found. Run `python generate_data.py` first."
        )
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        rows = json.load(f)
    return pd.DataFrame(rows)


def get_required_skills(role: str) -> list:
    return list(REQUIRED_SKILLS.get(role, []))


# ----- Trust + bucketing -----------------------------------------------------

def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def is_endorsement_trusted(endorsement: dict, current_date: str) -> bool:
    """Trusted iff (manager AND <= 6 months) OR (course AND <= 2 years)."""
    try:
        d = _parse_date(endorsement["date"])
        now = _parse_date(current_date)
    except (KeyError, ValueError):
        return False
    age_days = (now - d).days
    src = endorsement.get("source")
    if src == "manager" and age_days <= 183:  # ~6 months
        return True
    if src == "course" and age_days <= 730:  # 2 years
        return True
    return False


def _endorsements_for(skill: str, endorsements: list) -> list:
    return [e for e in endorsements if e.get("skill") == skill]


def _has_skill_at_proficiency(skill: str, endorsements: list, min_prof: int) -> bool:
    return any(
        e.get("proficiency", 0) >= min_prof
        for e in _endorsements_for(skill, endorsements)
    )


def _has_trusted_endorsement(skill: str, endorsements: list,
                             current_date: str, min_prof: int = 1) -> bool:
    return any(
        is_endorsement_trusted(e, current_date) and e.get("proficiency", 0) >= min_prof
        for e in _endorsements_for(skill, endorsements)
    )


def _classify(employee: dict, required: list, current_date: str) -> str | None:
    """Return one of: 'confirmed', 'one_course_away', 'needs_verification', or None.

    Buckets are checked in priority order; an employee lands in the first
    one that matches.
    """
    endorsements = employee.get("endorsements", [])
    skills = set(employee.get("skills", []))

    # Bucket 1: confirmed. Has every required skill at >=3 AND trusted.
    if all(s in skills for s in required):
        all_trusted_at_three = all(
            _has_skill_at_proficiency(s, endorsements, 3)
            and _has_trusted_endorsement(s, endorsements, current_date, min_prof=3)
            for s in required
        )
        if all_trusted_at_three:
            return "confirmed"

    # Bucket 2: one_course_away. Missing exactly one required skill,
    # all the OTHERS at >=3 trusted.
    missing = [s for s in required if s not in skills]
    if len(missing) == 1:
        present = [s for s in required if s in skills]
        if all(
            _has_skill_at_proficiency(s, endorsements, 3)
            and _has_trusted_endorsement(s, endorsements, current_date, min_prof=3)
            for s in present
        ):
            return "one_course_away"

    # Bucket 3: needs_verification. Has all required skills (any prof),
    # but at least one is only untrusted.
    if all(s in skills for s in required):
        any_untrusted_only = any(
            not _has_trusted_endorsement(s, endorsements, current_date, min_prof=1)
            for s in required
        )
        if any_untrusted_only:
            return "needs_verification"

    return None


# ----- Plan computation ------------------------------------------------------

def compute_plan(role: str, target_headcount: int, budget: float) -> dict:
    df = load_data()
    required = get_required_skills(role)

    title_count = int((df["job_title"] == role).sum())

    confirmed_ids: list[str] = []
    in_role_confirmed_ids: list[str] = []
    movable_confirmed_ids: list[str] = []
    needs_verification_ids: list[str] = []
    one_course_away_ids: list[str] = []

    confirmed_records = []  # for attrition

    for _, row in df.iterrows():
        emp = row.to_dict()
        bucket = _classify(emp, required, CURRENT_DATE)
        if bucket == "confirmed":
            confirmed_ids.append(emp["id"])
            confirmed_records.append(emp)
            if emp["job_title"] == role:
                in_role_confirmed_ids.append(emp["id"])
            else:
                movable_confirmed_ids.append(emp["id"])
        elif bucket == "one_course_away":
            one_course_away_ids.append(emp["id"])
        elif bucket == "needs_verification":
            needs_verification_ids.append(emp["id"])

    # Attrition: sum of flight_risk for confirmed (default fill), capped.
    attrition_sum = 0.0
    for emp in confirmed_records:
        fr = emp.get("flight_risk")
        # pandas reads JSON null as NaN; treat both as missing.
        if fr is None or (isinstance(fr, float) and fr != fr):
            fr = DEFAULT_FLIGHT_RISK
        attrition_sum += fr
    attrition = int(round(attrition_sum))
    attrition = min(attrition, len(confirmed_ids))

    # 3-year erosion of the confirmed pool. A quiet acknowledgement of
    # the multi-year horizon, not a simulation. Borrowed from the
    # workforcedecisions Low/Med/High mapping.
    avg_flight = (
        attrition_sum / len(confirmed_records) if confirmed_records else DEFAULT_FLIGHT_RISK
    )
    confirmed_in_3yr = int(round(len(confirmed_ids) * (1 - avg_flight) ** 3))

    confirmed_after_attrition = len(confirmed_ids) - attrition
    hire_gap = max(
        0,
        target_headcount - confirmed_after_attrition - len(one_course_away_ids),
    )

    move_cost = len(movable_confirmed_ids) * MOVE_COST
    reskill_cost = len(one_course_away_ids) * RESKILL_COST
    hire_cost = hire_gap * HIRE_COST
    verify_cost = len(needs_verification_ids) * VERIFY_COST
    plan_cost = move_cost + reskill_cost + hire_cost + verify_cost

    hire_all_cost = target_headcount * HIRE_COST
    savings = hire_all_cost - plan_cost
    savings_percent = (round((savings / hire_all_cost) * 100, 1)
                       if hire_all_cost > 0 else 0.0)

    over_budget = plan_cost > budget
    remaining_budget = budget - plan_cost
    budget_options = None
    if over_budget:
        shortfall = plan_cost - budget
        option_a_cost = move_cost + reskill_cost
        option_b_new_target = max(
            0,
            confirmed_after_attrition + len(one_course_away_ids)
            + math.floor(max(0, budget - move_cost - reskill_cost) / HIRE_COST),
        )
        option_c_request = shortfall
        budget_options = {
            "A": {
                "description": (
                    f"Prioritize internal actions (${option_a_cost / 1e6:.1f}M), "
                    f"defer hiring"
                ),
                "cost": option_a_cost,
            },
            "B": {
                "description": f"Reduce target to {option_b_new_target}",
                "target": option_b_new_target,
            },
            "C": {
                "description": (
                    f"Request additional ${shortfall / 1e6:.1f}M "
                    f"(escalate to CFO)"
                ),
                "request": option_c_request,
            },
            "recommended": "A",
        }

    # Data quality across the whole dataset.
    total_endorsements = 0
    self_or_inferred = 0
    stale = 0
    now = _parse_date(CURRENT_DATE)
    for _, row in df.iterrows():
        for e in row.get("endorsements", []) or []:
            total_endorsements += 1
            if e.get("source") in ("self", "inference"):
                self_or_inferred += 1
            try:
                if (now - _parse_date(e["date"])).days > 730:
                    stale += 1
            except (KeyError, ValueError):
                pass
    pct_self_declared = round(
        (self_or_inferred / total_endorsements) * 100, 1
    ) if total_endorsements else 0.0
    pct_stale = round(
        (stale / total_endorsements) * 100, 1
    ) if total_endorsements else 0.0

    return {
        "role": role,
        "target_headcount": target_headcount,
        "title_count": title_count,
        "confirmed": confirmed_ids,
        "in_role_confirmed": in_role_confirmed_ids,
        "movable_confirmed": movable_confirmed_ids,
        "needs_verification": needs_verification_ids,
        "one_course_away": one_course_away_ids,
        "attrition": attrition,
        "confirmed_in_3yr": confirmed_in_3yr,
        # Soft supply = confirmed + needs_verification (ceiling if every
        # weak signal is later confirmed by a manager).
        "supply_firm": len(confirmed_ids),
        "supply_soft": len(confirmed_ids) + len(needs_verification_ids),
        "hire_gap": hire_gap,
        "plan_cost": float(plan_cost),
        "move_cost": float(move_cost),
        "reskill_cost": float(reskill_cost),
        "hire_cost": float(hire_cost),
        "verify_cost": float(verify_cost),
        "hire_all_cost": float(hire_all_cost),
        "remaining_budget": float(remaining_budget),
        "savings": float(savings),
        "savings_percent": float(savings_percent),
        "over_budget": bool(over_budget),
        "budget_options": budget_options,
        "data_quality": {
            "pct_self_declared": pct_self_declared,
            "pct_stale": pct_stale,
        },
    }


def employee_lookup() -> dict:
    """Return id -> {name, job_title, department} for chat answers."""
    df = load_data()
    return {
        row["id"]: {
            "name": row["name"],
            "job_title": row["job_title"],
            "department": row["department"],
        }
        for _, row in df.iterrows()
    }


def people_for_action(action_kind: str, role: str, ids: list) -> list[dict]:
    """Given an action kind and a list of employee ids, return per-row
    dicts the UI can render directly into a table:

      {name, job_title, department, context}

    'context' is the action-specific column:
      - move:    "Has all required skills"
      - reskill: the missing required skill (e.g. "ETL")
      - verify:  short reason why the match is ambiguous
    """
    df = load_data()
    by_id = {row["id"]: row.to_dict() for _, row in df.iterrows()}
    required = REQUIRED_SKILLS.get(role, [])
    out = []
    for emp_id in ids:
        emp = by_id.get(emp_id)
        if not emp:
            continue
        endorsements = emp.get("endorsements") or []
        skills = set(emp.get("skills") or [])

        if action_kind == "move":
            context = "All required skills verified"
        elif action_kind == "reskill":
            missing = [s for s in required if s not in skills]
            context = f"Missing: {missing[0]}" if missing else "Missing: -"
        elif action_kind == "verify":
            # Identify which required skill has only weak endorsements.
            weak = []
            for s in required:
                trusted = any(
                    is_endorsement_trusted(e, CURRENT_DATE)
                    for e in endorsements if e.get("skill") == s
                )
                if not trusted and any(e.get("skill") == s for e in endorsements):
                    weak.append(s)
            if weak:
                if len(weak) == 1:
                    context = f"Weak signal on {weak[0]}"
                else:
                    context = f"Weak signal on {weak[0]} +{len(weak)-1} more"
            else:
                context = "Needs manager confirmation"
        else:
            context = ""

        out.append({
            "id": emp_id,
            "name": emp.get("name", ""),
            "job_title": emp.get("job_title", ""),
            "department": emp.get("department", ""),
            "context": context,
        })
    return out


# Action timelines (months) borrowed from the workforcedecisions
# action_assumptions table. Move is fastest, hire is slowest.
ACTION_MONTHS = {
    "move": 2,
    "reskill": 4,
    "verify": 1,
    "hire": 6,
}

# Defensible breakdown for each timeline. Components sum to the months
# above (4 weeks ~= 1 month). Surfaced inline in the UI so executives
# can see how the number was built.
ACTION_BREAKDOWN = {
    "move":    "2 wk transition + 6 wk role ramp",
    "reskill": "2 wk enrollment + 10 wk course + 4 wk on-the-job",
    "verify":  "Manager review cycle",
    "hire":    "6 wk req approval + 12 wk pipeline + 4 wk start + 4 wk ramp",
}


def months_until(deadline: str, current_date: str = CURRENT_DATE) -> int:
    """Months from current_date to a "YYYY Q[1-4]" deadline.

    Approximates a quarter as 3 months from the current point.
    """
    try:
        year_s, q_s = deadline.split()
        year = int(year_s)
        quarter = int(q_s.replace("Q", ""))
    except (ValueError, AttributeError):
        return 36
    # End-of-quarter month: Q1=3, Q2=6, Q3=9, Q4=12.
    end_month = quarter * 3
    now = _parse_date(current_date)
    months = (year - now.year) * 12 + (end_month - now.month)
    return max(0, months)

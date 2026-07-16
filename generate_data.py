"""
Mock workforce data generator.

Produces workforce_data.json with 200 employees distributed across
five job titles. Deterministic via seed 42. Endorsement quality is
intentionally messy: ~40% self/inferred, ~15% stale, duplicates, gaps.
"""

import json
import random
from datetime import datetime, timedelta

SEED = 42
TOTAL_EMPLOYEES = 200
CURRENT_DATE = datetime(2026, 6, 20)

ROLE_DISTRIBUTION = {
    "AI Engineer": 25,
    "Data Engineer": 50,
    "Platform Engineer": 40,
    "Backend Engineer": 50,
    "Legacy System Admin": 35,
}

# Skills associated with each role (more than the strict required set,
# so some employees have a partial match).
ROLE_SKILL_POOL = {
    "AI Engineer": ["Python", "MLOps", "LLM Integration", "System Design",
                    "PyTorch", "TensorFlow", "Vector DBs"],
    "Data Engineer": ["Python", "SQL", "Spark", "ETL",
                      "Airflow", "dbt", "Snowflake"],
    "Platform Engineer": ["Kubernetes", "Terraform", "CI/CD", "System Design",
                          "AWS", "Linux", "Helm"],
    "Backend Engineer": ["Java", "Spring", "System Design", "SQL",
                         "Kafka", "REST", "gRPC"],
    "Legacy System Admin": ["COBOL", "JCL", "Mainframe", "Batch Processing",
                            "DB2", "z/OS"],
}

ROLE_DEPARTMENTS = {
    "AI Engineer": ["AI Platform", "ML Research", "Applied AI"],
    "Data Engineer": ["Data Platform", "Analytics", "Data Infrastructure"],
    "Platform Engineer": ["Cloud Platform", "DevOps", "Infrastructure"],
    "Backend Engineer": ["Core Services", "Payments", "Identity"],
    "Legacy System Admin": ["Mainframe Ops", "Core Banking", "Legacy Systems"],
}

FIRST_NAMES = [
    "Amara", "Liang", "Priya", "Kofi", "Sofia", "Hiroshi", "Aisha",
    "Diego", "Yuki", "Olumide", "Anika", "Mateo", "Zara", "Kenji",
    "Femi", "Ines", "Dimitri", "Layla", "Tomas", "Nadia", "Rohan",
    "Ingrid", "Sanjay", "Mei", "Tariq", "Beatrice", "Jin", "Esther",
    "Rashid", "Camila", "Bjorn", "Aaliyah", "Niko", "Saskia", "Omar",
    "Linnea", "Arjun", "Fatima", "Hugo", "Naledi", "Pavel", "Maya",
    "Cyrus", "Adaeze", "Lukas", "Kira", "Joaquin", "Suri", "Idris", "Elena",
]

LAST_NAMES = [
    "Okonkwo", "Tanaka", "Patel", "Mensah", "Rossi", "Yamamoto",
    "Khan", "Garcia", "Sato", "Adeyemi", "Sharma", "Lopez",
    "Bashir", "Suzuki", "Ojo", "Costa", "Ivanov", "Hassan",
    "Silva", "Petrova", "Kapoor", "Lindgren", "Iyer", "Chen",
    "Mahmoud", "Bianchi", "Park", "Mwangi", "Aziz", "Diaz",
    "Olsen", "Robinson", "Aaltonen", "Kowalski", "Saleh",
    "Bergman", "Nair", "Haddad", "Schmidt", "Dlamini",
    "Novak", "Ramirez", "Farahani", "Eze", "Becker", "Sokolova",
    "Vargas", "Nguyen", "El-Sayed", "Petrov",
]


def _random_date_within_days(days: int, rng: random.Random) -> str:
    """Pick a date between (CURRENT_DATE - days) and CURRENT_DATE."""
    offset = rng.randint(0, days)
    d = CURRENT_DATE - timedelta(days=offset)
    return d.strftime("%Y-%m-%d")


def _random_date_older_than_days(min_days: int, rng: random.Random) -> str:
    """Pick a date between (CURRENT_DATE - 5y) and (CURRENT_DATE - min_days)."""
    offset = rng.randint(min_days, 5 * 365)
    d = CURRENT_DATE - timedelta(days=offset)
    return d.strftime("%Y-%m-%d")


def _pick_skills(role: str, rng: random.Random) -> tuple:
    """Choose a subset of role-relevant skills for this employee.

    Returns (skills, profile) so the caller knows whether this person
    should be a confirmed-bucket target or a one-course-away target.
    """
    pool = ROLE_SKILL_POOL[role]
    required = pool[:4]  # First four are the required set
    extras = pool[4:]

    # Coverage profile chosen so the buckets land in interesting ratios.
    profile = rng.choices(
        ["full", "missing_one", "missing_more", "partial_extras"],
        weights=[55, 20, 15, 10],
        k=1,
    )[0]

    if profile == "full":
        skills = list(required)
    elif profile == "missing_one":
        skills = list(required)
        skills.pop(rng.randrange(len(skills)))
    elif profile == "missing_more":
        keep = rng.randint(1, max(1, len(required) - 2))
        skills = rng.sample(required, keep)
    else:  # partial_extras: some required + extras
        keep = rng.randint(2, len(required) - 1)
        skills = rng.sample(required, keep)
        skills += rng.sample(extras, rng.randint(0, len(extras)))

    # Maybe sprinkle in one extra skill
    if extras and rng.random() < 0.3:
        e = rng.choice(extras)
        if e not in skills:
            skills.append(e)

    return skills, profile


def _make_endorsements(skills: list, rng: random.Random,
                       confirmed_target: bool = False) -> list:
    """Build endorsements for an employee's skills.

    Rules from the spec:
      - ~40% of endorsements are self/inference
      - ~15% older than 2 years
      - manager endorsements mostly ≤6 months but some stale
      - some employees have duplicate endorsements (one trusted, one not)

    When ``confirmed_target`` is True the employee is intended to clear the
    "confirmed" bucket — every skill gets at least one trusted (manager,
    ≤6 months OR course, ≤2 years) endorsement at proficiency ≥3. Other
    employees still get the messy mix, so the verify / one-course-away
    buckets stay populated.
    """
    endorsements = []
    for skill in skills:
        # Baseline endorsement — random source/date.
        roll = rng.random()
        if roll < 0.40:
            source = rng.choice(["self", "inference"])
        elif roll < 0.85:
            source = "manager"
        else:
            source = "course"

        stale = rng.random() < 0.15
        if stale:
            date = _random_date_older_than_days(2 * 365 + 1, rng)
        else:
            if source == "manager":
                if rng.random() < 0.15:
                    date = _random_date_older_than_days(181, rng)
                else:
                    date = _random_date_within_days(180, rng)
            elif source == "course":
                date = _random_date_within_days(2 * 365, rng)
            else:
                date = _random_date_within_days(3 * 365, rng)

        proficiency = rng.choices([1, 2, 3, 4, 5],
                                  weights=[5, 15, 35, 30, 15], k=1)[0]

        endorsements.append({
            "skill": skill,
            "proficiency": proficiency,
            "source": source,
            "date": date,
        })

        # If this employee is supposed to be confirmable, layer a guaranteed
        # trusted endorsement on top — manager, recent, proficiency ≥3.
        if confirmed_target:
            endorsements.append({
                "skill": skill,
                "proficiency": rng.choice([3, 4, 4, 5]),
                "source": "manager",
                "date": _random_date_within_days(170, rng),
            })

        # Duplicate endorsement chance — many employees have a stale or
        # self-declared endorsement layered on top of the trusted one.
        # Tuned to push the global self/inferred share toward ~40%.
        if rng.random() < 0.55:
            alt_source = rng.choices(
                ["self", "inference", "manager"],
                weights=[45, 35, 20], k=1,
            )[0]
            if alt_source == "manager":
                alt_date = (_random_date_older_than_days(190, rng)
                            if rng.random() < 0.6
                            else _random_date_within_days(180, rng))
            else:
                alt_date = _random_date_within_days(3 * 365, rng)
            endorsements.append({
                "skill": skill,
                "proficiency": rng.choices([1, 2, 3, 4, 5],
                                           weights=[5, 15, 35, 30, 15], k=1)[0],
                "source": alt_source,
                "date": alt_date,
            })

    return endorsements


def generate() -> list:
    rng = random.Random(SEED)
    employees = []

    # Build the full role list expanded by counts.
    role_sequence = []
    for role, count in ROLE_DISTRIBUTION.items():
        role_sequence.extend([role] * count)
    rng.shuffle(role_sequence)

    # Indices of employees that will have null flight_risk (~10%).
    null_flight_idxs = set(rng.sample(range(TOTAL_EMPLOYEES), 20))

    # Pre-build a manager pool.
    manager_ids = [f"MGR{str(i).zfill(3)}" for i in range(1, 26)]

    for i in range(TOTAL_EMPLOYEES):
        emp_id = f"EMP{str(i + 1).zfill(3)}"
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        role = role_sequence[i]
        department = rng.choice(ROLE_DEPARTMENTS[role])
        manager_id = rng.choice(manager_ids)

        if i in null_flight_idxs:
            flight_risk = None
        else:
            # Most people are low-risk; a tail of higher risk.
            flight_risk = round(rng.choices(
                [rng.uniform(0.02, 0.10),
                 rng.uniform(0.10, 0.25),
                 rng.uniform(0.25, 0.55)],
                weights=[55, 30, 15], k=1)[0], 2)

        retirement_eligible = rng.random() < 0.05
        skills, profile = _pick_skills(role, rng)

        # ~12% of employees are "cross-trained" — they fully match the
        # required skills for a *different* role. This makes the "movable
        # to {role}" bucket non-empty and gives the executive a real
        # internal-action option.
        cross_role = None
        if rng.random() < 0.12:
            other_roles = [r for r in ROLE_DISTRIBUTION if r != role]
            cross_role = rng.choice(other_roles)
            cross_required = ROLE_SKILL_POOL[cross_role][:4]
            for s in cross_required:
                if s not in skills:
                    skills.append(s)

        # ~70% of "full"-skill employees and ~85% of "missing_one" employees
        # get the trusted-endorsement boost so the confirmed and
        # one-course-away buckets actually populate. Cross-trained
        # employees are confirmed-targets for BOTH skill sets.
        if cross_role is not None:
            confirmed_target = rng.random() < 0.85
        elif profile == "full":
            confirmed_target = rng.random() < 0.70
        elif profile == "missing_one":
            confirmed_target = rng.random() < 0.85
        else:
            confirmed_target = False
        endorsements = _make_endorsements(skills, rng,
                                          confirmed_target=confirmed_target)

        employees.append({
            "id": emp_id,
            "name": f"{first} {last}",
            "job_title": role,
            "department": department,
            "manager_id": manager_id,
            "flight_risk": flight_risk,
            "retirement_eligible": retirement_eligible,
            "skills": skills,
            "endorsements": endorsements,
        })

    return employees


def main():
    employees = generate()
    with open("workforce_data.json", "w", encoding="utf-8") as f:
        json.dump(employees, f, indent=2)
    print(f"Wrote workforce_data.json ({len(employees)} employees).")


if __name__ == "__main__":
    main()

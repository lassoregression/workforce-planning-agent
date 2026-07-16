"""
Streamlit workforce planning agent.

Briefing tool for a CHRO with 90 seconds: thesis on top, savings as
the page's typographic anchor, sources and provenance inline. No
analyst tables, no decoration.
"""

from __future__ import annotations

import streamlit as st

from engine import (
    ACTION_BREAKDOWN,
    ACTION_MONTHS,
    COURSE_NAMES,
    REQUIRED_SKILLS,
    compute_plan,
    employee_lookup,
    months_until,
    people_for_action,
)
from llm_utils import chat_response, generate_headline, generate_risk

# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Workforce Plan",
    page_icon=":bar_chart:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DEFAULTS = {
    "role": "AI Engineer",
    "target": 250,
    "year": "2027 Q4",
    "budget": 12_000_000,
}


# ----- Formatting helpers ---------------------------------------------------

def format_dollars(amount: float) -> str:
    if amount is None:
        return "-"
    if abs(amount) >= 1e6:
        return f"${amount / 1e6:.1f}M"
    return f"${amount / 1e3:.0f}K"


def format_budget(n: float) -> str:
    """Compact form for the budget input. Always 1 decimal at $M scale."""
    if n >= 1e6:
        return f"${n / 1e6:.1f}M"
    if n >= 1e3:
        return f"${n / 1e3:.0f}K"
    return f"${int(n)}"


def parse_budget(s: str) -> float | None:
    """Accept '$12M', '12M', '12.5m', '$500K', '12,000,000', '12000000'.

    Returns None on unparseable input so the caller can keep the last
    valid value.
    """
    if s is None:
        return None
    s = s.strip().lower().replace("$", "").replace(",", "").replace(" ", "")
    if not s:
        return None
    multiplier = 1.0
    if s.endswith("m"):
        multiplier = 1e6
        s = s[:-1]
    elif s.endswith("k"):
        multiplier = 1e3
        s = s[:-1]
    elif s.endswith("b"):
        multiplier = 1e9
        s = s[:-1]
    try:
        return float(s) * multiplier
    except ValueError:
        return None


# Collective noun used in narrative sentences. "engineers" reads wrong
# for Legacy System Admin, so each role names its own.
ROLE_COLLECTIVE = {
    "AI Engineer": "engineers",
    "Data Engineer": "engineers",
    "Platform Engineer": "engineers",
    "Backend Engineer": "engineers",
    "Legacy System Admin": "admins",
}


def role_collective(role: str) -> str:
    """Lower-case collective noun for the role; defaults to 'people'."""
    return ROLE_COLLECTIVE.get(role, "people")


def role_plural_title(role: str) -> str:
    """Title-cased plural of the role for use in sentences. 'AI Engineers'."""
    return role + "s"


def confidence_dot(level: str) -> str:
    """Inline colored dot (replaces the pill in pass 2)."""
    palette = {
        "high": "#15803D",
        "medium": "#A16207",
        "low": "#B91C1C",
        "neutral": "#9A9A95",
    }
    return (
        f"<span style='display:inline-block;width:9px;height:9px;"
        f"border-radius:50%;background:{palette.get(level, palette['neutral'])};"
        f"margin-right:0.5rem;vertical-align:1px;'></span>"
    )


# ----- Styling --------------------------------------------------------------

DISPLAY = "Georgia, 'Iowan Old Style', 'Apple Garamond', serif"
BODY = "-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace"

CSS = f"""
<style>
/* Hide Streamlit's chrome: Deploy button, header, decoration bar, menu */
[data-testid="stToolbar"], [data-testid="stDecoration"],
header[data-testid="stHeader"] {{ display: none !important; }}
#MainMenu, footer {{ visibility: hidden; }}

html, body, .stApp, .main, [data-testid="stAppViewContainer"] {{
  background: #FAFAF7 !important;
  color: #0A0A0A;
  font-family: {BODY};
}}
.block-container {{ padding-top: 2.2rem; max-width: 1080px; }}

.eyebrow {{
  font-family: {MONO};
  font-size: 0.74rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #6B6B6B;
  margin: 0 0 1.4rem 0;
}}
.eyebrow .sep {{ color: #9A9A95; margin: 0 0.6rem; }}

.thesis {{
  font-family: {DISPLAY};
  font-size: 2.6rem;
  line-height: 1.15;
  font-weight: 500;
  letter-spacing: -0.015em;
  color: #0A0A0A;
  margin: 0 0 1.0rem 0;
  max-width: 820px;
}}
.thesis-support {{
  font-family: {BODY};
  font-size: 1.05rem;
  line-height: 1.55;
  color: #6B6B6B;
  max-width: 760px;
  margin: 0 0 2.4rem 0;
}}
.thesis-support .num {{ font-family: {MONO}; color: #0A0A0A; }}

.section-h {{
  font-family: {MONO};
  font-size: 0.74rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #6B6B6B;
  margin: 2.6rem 0 0.8rem 0;
  padding-top: 0.7rem;
  border-top: 1px solid #E8E4DA;
  display: flex;
  align-items: center;
  gap: 0.7rem;
}}
.section-h.signature {{ color: #0A0A0A; }}

/* RISK level pill, used inside the section-h for the risk section */
.risk-pill {{
  font-family: {MONO};
  font-size: 0.70rem;
  letter-spacing: 0.10em;
  padding: 0.10rem 0.5rem;
  border: 1px solid currentColor;
  border-radius: 2px;
}}
.risk-pill.high   {{ color: #B91C1C; }}
.risk-pill.medium {{ color: #A16207; }}
.risk-pill.low    {{ color: #15803D; }}

.supply-lead {{
  font-family: {DISPLAY};
  font-size: 1.4rem;
  line-height: 1.4;
  color: #0A0A0A;
  margin: 0.4rem 0 1.2rem 0;
  max-width: 760px;
}}
.supply-lead .num {{ font-family: {MONO}; font-weight: 500; }}

/* Generic data-table treatment shared by supply, gap, plan, financial */
table.data {{
  width: 100%;
  border-collapse: collapse;
  margin: 0.6rem 0 0.4rem 0;
}}
table.data th {{
  font-family: {MONO};
  font-size: 0.70rem;
  text-transform: uppercase;
  letter-spacing: 0.10em;
  color: #6B6B6B;
  font-weight: 500;
  text-align: left;
  padding: 0.45rem 0.7rem 0.45rem 0;
  border-bottom: 1px solid #0A0A0A;
}}
table.data th.num, table.data td.num {{
  text-align: right;
  font-family: {MONO};
  font-variant-numeric: tabular-nums;
}}
table.data td {{
  padding: 0.55rem 0.7rem 0.55rem 0;
  border-bottom: 1px solid #E8E4DA;
  vertical-align: top;
  font-size: 0.95rem;
  color: #0A0A0A;
}}
table.data td.muted, table.data td.muted .v {{ color: #6B6B6B; }}
table.data td.source {{
  color: #6B6B6B;
  font-size: 0.86rem;
  line-height: 1.4;
}}
table.data tr.total td {{
  font-weight: 600;
  border-top: 1px solid #0A0A0A;
  border-bottom: none;
  padding-top: 0.65rem;
}}
table.data tr.subrow td {{
  padding: 0 0.7rem 0.7rem 0;
  border-bottom: 1px solid #E8E4DA;
  font-family: {MONO};
  font-size: 0.78rem;
  color: #6B6B6B;
}}
table.data tr.subrow td.spacer {{ border: none; }}

/* Gap row: render as a single-row table so the numbers line up under
   their labels regardless of digit count. */
table.gap td {{
  padding: 0.45rem 1.6rem 0 0;
  border: none;
  font-family: {DISPLAY};
  font-size: 1.9rem;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  color: #0A0A0A;
  line-height: 1;
}}
table.gap td.dim {{ color: #6B6B6B; }}
table.gap th {{
  border: none;
  padding: 0 1.6rem 0.4rem 0;
}}

.erosion-line {{
  font-size: 0.86rem;
  color: #6B6B6B;
  margin-top: 1.0rem;
  padding-top: 0.8rem;
  border-top: 1px dashed #E8E4DA;
}}
.erosion-line .num {{ font-family: {MONO}; color: #0A0A0A; }}

.savings-block {{
  text-align: left;
  padding: 1.8rem 0 1.2rem 0;
  margin: 0.6rem 0 1.4rem 0;
  border-top: 1px solid #0A0A0A;
  border-bottom: 1px solid #0A0A0A;
}}
.savings-amount {{
  font-family: {DISPLAY};
  font-size: 6.0rem;
  font-weight: 500;
  letter-spacing: -0.04em;
  line-height: 0.95;
  color: #15803D;
  font-variant-numeric: tabular-nums;
  margin: 0;
}}
.savings-amount.negative {{ color: #B91C1C; }}
.savings-caption {{
  font-family: {BODY};
  font-size: 1.0rem;
  line-height: 1.5;
  color: #0A0A0A;
  max-width: 640px;
  margin-top: 1.0rem;
}}
.savings-caption .num {{ font-family: {MONO}; }}
.savings-caption .muted {{ color: #6B6B6B; }}

/* Plan-table specifics */
table.plan td.idx {{
  font-family: {DISPLAY};
  font-size: 1.5rem;
  font-weight: 500;
  color: #6B6B6B;
  width: 2.6rem;
}}
table.plan td.action {{ font-size: 1.0rem; }}
table.plan td.action strong {{ font-weight: 600; }}
table.plan td.action .num {{ font-family: {MONO}; }}
table.plan td.timing {{
  font-family: {MONO};
  font-size: 0.86rem;
  white-space: nowrap;
  color: #6B6B6B;       /* neutral by default; only late stays red */
  text-align: right;
}}
table.plan td.timing.late .timing-headline {{ color: #B91C1C; }}
table.plan td.timing .timing-headline {{
  font-size: 0.95rem;
  color: #0A0A0A;
}}
table.plan td.timing .timing-breakdown {{
  font-size: 0.74rem;
  color: #9A9A95;
  margin-top: 0.15rem;
}}
table.plan td.count.num {{ width: 4rem; }}

/* Risk text: plain section, no left border */
.risk-text {{
  font-size: 0.96rem;
  line-height: 1.55;
  color: #0A0A0A;
  margin: 0.4rem 0 0 0;
  max-width: 820px;
}}
.data-quality {{
  font-family: {MONO};
  font-size: 0.78rem;
  color: #9A9A95;
  margin-top: 0.6rem;
}}

.budget-warn {{
  margin: 1.0rem 0;
  padding: 1rem 1.2rem;
  border: 1px solid #E8E4DA;
  background: #FFFDF7;
  font-size: 0.96rem;
  color: #0A0A0A;
}}
.budget-warn .num {{ font-family: {MONO}; color: #B91C1C; }}

[data-testid="stWidgetLabel"] p {{
  font-family: {MONO} !important;
  font-size: 0.72rem !important;
  text-transform: uppercase;
  letter-spacing: 0.10em;
  color: #6B6B6B !important;
}}
details summary {{
  font-family: {MONO};
  font-size: 0.78rem;
  letter-spacing: 0.06em;
  color: #6B6B6B !important;
}}
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)


# ----- Session state seed ----------------------------------------------------

for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)


def _recompute():
    plan = compute_plan(
        st.session_state["role"],
        int(st.session_state["target"]),
        float(st.session_state["budget"]),
    )
    st.session_state["plan"] = plan
    st.session_state["headline"] = generate_headline(plan, st.session_state["year"])
    st.session_state["risk_text"] = generate_risk(plan)


def _on_budget_change():
    """Parse the formatted text in budget_text and update the budget float.

    Falls back to the prior valid budget on parse failure and surfaces
    a small caption error.
    """
    raw = st.session_state.get("budget_text", "")
    parsed = parse_budget(raw)
    if parsed is not None and parsed >= 0:
        st.session_state["budget"] = parsed
        st.session_state["budget_text"] = format_budget(parsed)
        st.session_state["budget_error"] = None
    else:
        st.session_state["budget_error"] = (
            "Enter like $12M, $500K, or 12000000."
        )
    _recompute()


if "plan" not in st.session_state:
    _recompute()
    st.session_state.setdefault("chat_history", [])
    st.session_state.setdefault("lookup", employee_lookup())
    st.session_state.setdefault("budget_text", format_budget(DEFAULTS["budget"]))
    st.session_state.setdefault("budget_error", None)


plan = st.session_state["plan"]
role = plan["role"]
required = REQUIRED_SKILLS[role]
year = st.session_state["year"]


# ----- Eyebrow + headline thesis (HERO) --------------------------------------

st.markdown(
    f"<div class='eyebrow'>Workforce plan"
    f"<span class='sep'>/</span>{role}"
    f"<span class='sep'>/</span>{plan['target_headcount']} by {year}</div>",
    unsafe_allow_html=True,
)

headline = st.session_state["headline"]
if isinstance(headline, dict):
    thesis = headline.get("thesis", "")
else:
    thesis = headline

st.markdown(f"<h1 class='thesis'>{thesis}</h1>", unsafe_allow_html=True)


# Build a dynamic support sentence that adapts to the plan numbers.
# Drop clauses that are zero so we never say "move 0".
def _build_support(plan: dict, year: str, role: str) -> str:
    movable = len(plan["movable_confirmed"])
    develop = len(plan["one_course_away"])
    hire = plan["hire_gap"]
    role_plural = role + "s"
    plan_cost = plan["plan_cost"]
    hire_all = plan["hire_all_cost"]
    target = plan["target_headcount"]
    deadline_months_left = months_until(year)
    longest_action_month = ACTION_MONTHS["hire"] if hire > 0 else (
        ACTION_MONTHS["reskill"] if develop > 0 else ACTION_MONTHS["move"]
    )
    on_track = longest_action_month <= deadline_months_left

    clauses = []
    if movable > 0:
        coll = role_collective(role)
        # Drop trailing 's' for n=1 ("engineers" -> "engineer", "admins" -> "admin").
        coll_form = coll[:-1] if movable == 1 and coll.endswith("s") else coll
        clauses.append(
            f"move {movable} confirmed {coll_form} from other teams"
        )
    if develop > 0:
        clauses.append(f"reskill {develop} who are one course away")
    if hire > 0:
        clauses.append(f"hire {hire} externally to close the gap")

    if not clauses:
        action_sentence = f"No new actions needed. The {target} {role_plural} target is already met."
    else:
        if len(clauses) == 1:
            joined = clauses[0]
        elif len(clauses) == 2:
            joined = f"{clauses[0]} and {clauses[1]}"
        else:
            joined = ", ".join(clauses[:-1]) + f", and {clauses[-1]}"
        action_sentence = joined[0].upper() + joined[1:] + "."

    cost_sentence = (
        f"Total cost <span class='num'>${plan_cost / 1e6:.1f}M</span>, "
        f"{'on track for' if on_track else 'will run past'} {year}."
    )
    compare_sentence = (
        f"Hiring all {target} externally would cost "
        f"<span class='num'>${hire_all / 1e6:.1f}M</span> and take 6 months."
    )
    return f"{action_sentence} {cost_sentence} {compare_sentence}"


support_html = _build_support(plan, year, role)
st.markdown(
    f"<p class='thesis-support'><strong>Plan.</strong> {support_html}</p>",
    unsafe_allow_html=True,
)


# ----- Inputs (quietly placed below the thesis) -----------------------------

bar = st.columns([2.0, 1.3, 1.3, 1.6])
with bar[0]:
    st.selectbox(
        "Role",
        list(REQUIRED_SKILLS.keys()),
        key="role",
        on_change=_recompute,
    )
with bar[1]:
    st.number_input(
        "Target headcount",
        min_value=1, max_value=1000,
        key="target",
        on_change=_recompute,
    )
with bar[2]:
    st.selectbox(
        "By when",
        ["2027 Q4", "2028 Q4", "2029 Q4"],
        key="year",
        on_change=_recompute,
    )
with bar[3]:
    st.text_input(
        "Budget",
        key="budget_text",
        on_change=_on_budget_change,
        help="Examples: $12M, $500K, 12000000",
    )
    if st.session_state.get("budget_error"):
        st.caption(st.session_state["budget_error"])


# ----- 1. SUPPLY ------------------------------------------------------------

st.markdown(
    "<div class='section-h'>Who's available today</div>",
    unsafe_allow_html=True,
)

firm = plan["supply_firm"]
title_count = plan["title_count"]
verify_count = len(plan["needs_verification"])
develop_count = len(plan["one_course_away"])

# Build a domain-specific lead sentence anchored in the actual numbers.
parts = [
    f"<span class='num'>{title_count}</span> employees hold the {role} title today, "
    f"and <span class='num'>{firm}</span> of them have every required skill verified "
    "by a manager (within 6 months) or a recent course (within 2 years)."
]
if verify_count > 0:
    parts.append(
        f"Another <span class='num'>{verify_count}</span> "
        f"{'looks' if verify_count == 1 else 'look'} qualified on paper but "
        f"{'needs' if verify_count == 1 else 'need'} a quick manager check. "
        f"Each confirmation removes 1 external hire."
    )
if develop_count > 0:
    plural = "is" if develop_count == 1 else "are"
    parts.append(
        f"<span class='num'>{develop_count}</span> "
        f"{plural} one course away from qualifying."
    )
lead = " ".join(parts)
st.markdown(
    f"<div class='supply-lead'>{lead}</div>",
    unsafe_allow_html=True,
)

provenance = {
    "title": f"Headcount in role from Employee Central, job_title = {role}.",
    "in_role": "Already in this role; all required skills trusted at proficiency 3+.",
    "movable": "In other teams; all required skills trusted. Cheapest, fastest action.",
    "verify": "Has the skills on paper, but only self-declared, inferred, or stale (>2y) endorsements.",
    "course": "Missing exactly 1 required skill; everything else trusted at 3+.",
}

rows = [
    ("Already in role", len(plan["in_role_confirmed"]), "high",
     provenance["in_role"]),
    ("In other teams (movable)", len(plan["movable_confirmed"]), "high",
     provenance["movable"]),
    ("One course away", len(plan["one_course_away"]), "medium",
     provenance["course"]),
    ("Match on paper, need verification", len(plan["needs_verification"]), "low",
     provenance["verify"]),
    ("Holding the title (any qualification)", plan["title_count"], "neutral",
     provenance["title"]),
]

supply_html = ["<table class='data'>"]
supply_html.append(
    "<tr>"
    "<th>Category</th>"
    "<th class='num'>Count</th>"
    "<th>How we know</th>"
    "</tr>"
)
for label, count, level, info in rows:
    supply_html.append(
        f"<tr>"
        f"<td>{confidence_dot(level)}{label}</td>"
        f"<td class='num'>{count}</td>"
        f"<td class='source'>{info}</td>"
        f"</tr>"
    )
supply_html.append("</table>")
st.markdown("\n".join(supply_html), unsafe_allow_html=True)


# ----- 2. GAP ---------------------------------------------------------------

st.markdown(
    f"<div class='section-h'>What it takes to reach {plan['target_headcount']}</div>",
    unsafe_allow_html=True,
)

confirmed_count = len(plan["confirmed"])

# Lead sentence: tie the row of numbers together in plain English.
gap_summary = (
    f"To reach <span class='num'>{plan['target_headcount']}</span>, "
    f"we'll lose <span class='num'>{plan['attrition']}</span> to attrition over 12 months "
    f"and rely on <span class='num'>{confirmed_count}</span> confirmed "
    f"plus <span class='num'>{len(plan['one_course_away'])}</span> developable "
    f"{role_collective(role)}. "
    f"That leaves <span class='num'>{plan['hire_gap']}</span> to hire externally."
)
st.markdown(
    f"<div class='supply-lead' style='font-size:1.1rem;margin-bottom:1.0rem;'>"
    f"{gap_summary}</div>",
    unsafe_allow_html=True,
)

gap_html = (
    "<table class='gap'>"
    "<tr>"
    "<th>Needed</th>"
    "<th>Confirmed today</th>"
    "<th>Attrition (1y)</th>"
    "<th>Developable</th>"
    "<th>Hire gap</th>"
    "</tr>"
    "<tr>"
    f"<td>{plan['target_headcount']}</td>"
    f"<td>{confirmed_count}</td>"
    f"<td class='dim'>-{plan['attrition']}</td>"
    f"<td>{len(plan['one_course_away'])}</td>"
    f"<td>{plan['hire_gap']}</td>"
    "</tr>"
    "</table>"
)
st.markdown(gap_html, unsafe_allow_html=True)

st.markdown(
    f"<div class='erosion-line'>At today's flight-risk rates, the "
    f"<span class='num'>{confirmed_count}</span> confirmed {role_collective(role)} "
    f"shrink to <span class='num'>~{plan['confirmed_in_3yr']}</span> over 3 years "
    f"if no one is replaced. Retention is half the workforce plan.</div>",
    unsafe_allow_html=True,
)


# ----- 3. SAVINGS HERO ------------------------------------------------------

st.markdown(
    "<div class='section-h signature'>Cost vs. hiring everyone</div>",
    unsafe_allow_html=True,
)

savings_neg = plan["savings"] < 0
amt_cls = "negative" if savings_neg else ""
direction = "cheaper" if not savings_neg else "more expensive"
st.markdown(
    f"""
    <div class='savings-block'>
      <div class='savings-amount {amt_cls}'>{format_dollars(abs(plan['savings']))}</div>
      <div class='savings-caption'>
        <span class='num'>{abs(plan['savings_percent'])}%</span> {direction} than hiring all
        <span class='num'>{plan['target_headcount']}</span> from outside.
        <span class='muted'>Plan <span class='num'>{format_dollars(plan['plan_cost'])}</span>
        vs. hire-all baseline <span class='num'>{format_dollars(plan['hire_all_cost'])}</span>.</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ----- 4. FINANCIAL DETAIL --------------------------------------------------

with st.expander("Show line items"):
    verify_n = len(plan["needs_verification"])
    fin_rows = [
        ("Budget allocated", format_dollars(st.session_state["budget"]), False, False),
        (f"Move {len(plan['movable_confirmed'])} x $6K",
         format_dollars(plan["move_cost"]), False, False),
        (f"Reskill {len(plan['one_course_away'])} x $8K",
         format_dollars(plan["reskill_cost"]), False, False),
        (f"Hire {plan['hire_gap']} x $45K",
         format_dollars(plan["hire_cost"]), False, False),
        (f"Verify {verify_n}", "$0", False, True),
        ("Total plan cost", format_dollars(plan["plan_cost"]), True, False),
        ("Remaining budget", format_dollars(plan["remaining_budget"]), False, True),
        ("Cost if you hire all 250 externally",
         format_dollars(plan["hire_all_cost"]), False, True),
    ]
    fin_html = ["<table class='data'>"]
    fin_html.append(
        "<tr><th>Item</th><th class='num'>Amount</th></tr>"
    )
    for label, value, total, muted in fin_rows:
        cls = "total" if total else ""
        muted_attr = " class='muted'" if muted and not total else ""
        fin_html.append(
            f"<tr class='{cls}'>"
            f"<td{muted_attr}>{label}</td>"
            f"<td class='num'{(' '+ muted_attr.strip()) if muted_attr else ''}>{value}</td>"
            f"</tr>"
        )
    fin_html.append("</table>")
    # Replace 250 in the "hire all" row with the actual target
    fin_html_str = "\n".join(fin_html).replace(
        "hire all 250 externally",
        f"hire all {plan['target_headcount']} externally",
    )
    st.markdown(fin_html_str, unsafe_allow_html=True)


# ----- 5. BUDGET CONSTRAINT (only if over) ----------------------------------

if plan["over_budget"] and plan["budget_options"]:
    st.markdown("<div class='section-h'>Budget shortfall</div>",
                unsafe_allow_html=True)
    shortfall = plan["plan_cost"] - st.session_state["budget"]
    st.markdown(
        f"<div class='budget-warn'>Plan cost "
        f"<span class='num'>{format_dollars(plan['plan_cost'])}</span> exceeds budget "
        f"<span class='num'>{format_dollars(st.session_state['budget'])}</span> by "
        f"<span class='num'>{format_dollars(shortfall)}</span>. "
        f"Choose how to close the gap.</div>",
        unsafe_allow_html=True,
    )
    options = plan["budget_options"]
    labels = [
        f"A. {options['A']['description']}",
        f"B. {options['B']['description']}",
        f"C. {options['C']['description']}",
    ]
    rec_idx = {"A": 0, "B": 1, "C": 2}.get(options.get("recommended", "A"), 0)
    st.radio("Options", labels, index=rec_idx, label_visibility="collapsed",
             key="budget_choice")


# ----- 6. RECOMMENDED ACTIONS -----------------------------------------------

st.markdown(
    "<div class='section-h'>What we'll do, in sequence</div>",
    unsafe_allow_html=True,
)

movable_n = len(plan["movable_confirmed"])
develop_n = len(plan["one_course_away"])
verify_n = len(plan["needs_verification"])
hire_n = plan["hire_gap"]
course = COURSE_NAMES[role]
deadline_months = months_until(year)
role_plural = role + "s"

actions = [
    {
        "verb": "Move",
        "count": movable_n,
        "tail": f"confirmed {role_collective(role)} from other teams.",
        "kind": "move",
        "ids": plan["movable_confirmed"],
        "context_col": "Why they qualify",
    },
    {
        "verb": "Enroll",
        "count": develop_n,
        "tail": f"in the <em>{course}</em> course.",
        "kind": "reskill",
        "ids": plan["one_course_away"],
        "context_col": "Skill to learn",
    },
    {
        "verb": "Verify",
        "count": verify_n,
        "tail": (
            "candidate with their manager. Each confirmation reduces hires by 1."
            if verify_n == 1
            else "candidates with their managers. Each confirmation reduces hires by 1."
        ),
        "kind": "verify",
        "ids": plan["needs_verification"],
        "context_col": "What's ambiguous",
    },
    {
        "verb": "Hire",
        "count": hire_n,
        "tail": f"{role_plural}.",
        "kind": "hire",
        "ids": [],
        "context_col": "",
    },
]

# Render one action per iteration: header row (as a small grid),
# breakdown caption, then the people-table expander right beneath it.
for i, a in enumerate(actions, start=1):
    months = ACTION_MONTHS[a["kind"]]
    on_time = months <= deadline_months
    timing_cls = "" if on_time else "late"
    timing_label = (
        f"~{months} mo" if on_time
        else f"~{months} mo (misses date)"
    )
    breakdown = ACTION_BREAKDOWN[a["kind"]]

    # Action header rendered as a single-row table so it lines up
    # column-for-column with the other actions visually. The timing
    # cell holds both the headline number and its breakdown so the
    # justification sits right next to the figure it justifies.
    st.markdown(
        f"<table class='data plan'>"
        f"<tr>"
        f"<td class='idx'>{i}</td>"
        f"<td class='action'><strong>{a['verb']}</strong> "
        f"<span class='num'>{a['count']}</span> {a['tail']}</td>"
        f"<td class='timing {timing_cls}'>"
        f"<div class='timing-headline'>{timing_label}</div>"
        f"<div class='timing-breakdown'>{breakdown}</div>"
        f"</td>"
        f"</tr>"
        f"</table>",
        unsafe_allow_html=True,
    )

    if a["ids"]:
        rows = people_for_action(a["kind"], role, a["ids"])
        with st.expander(f"See {len(rows)} "
                         f"{'person' if len(rows) == 1 else 'people'}"):
            ppl_html = ["<table class='data people'>"]
            ppl_html.append(
                "<tr>"
                "<th>Name</th>"
                "<th>Current role</th>"
                "<th>Department</th>"
                f"<th>{a['context_col']}</th>"
                "</tr>"
            )
            for r in rows[:50]:
                ppl_html.append(
                    f"<tr>"
                    f"<td>{r['name']}</td>"
                    f"<td>{r['job_title']}</td>"
                    f"<td>{r['department']}</td>"
                    f"<td class='source'>{r['context']}</td>"
                    f"</tr>"
                )
            ppl_html.append("</table>")
            st.markdown("\n".join(ppl_html), unsafe_allow_html=True)
            if len(rows) > 50:
                st.caption(f"...and {len(rows) - 50} more.")


# ----- 7. RISK + DATA QUALITY -----------------------------------------------

gap_size = plan["hire_gap"]
if gap_size > 30 or plan["confirmed_in_3yr"] < 0.6 * confirmed_count:
    level = "High"
elif gap_size > 10:
    level = "Medium"
else:
    level = "Low"

risk_pill_cls = level.lower()
st.markdown(
    f"<div class='section-h'>"
    f"<span>What happens if we delay</span>"
    f"<span class='risk-pill {risk_pill_cls}'>{level.upper()}</span>"
    f"</div>",
    unsafe_allow_html=True,
)

# Build a plain-English risk paragraph anchored in the actual numbers.
# Two distinct risks, two short sentences. No "engineer" hardcoding.
dq = plan["data_quality"]
collective = role_collective(role)
risk_paragraph = (
    f"<strong>Attrition.</strong> "
    f"We expect <span class='num'>{plan['attrition']}</span> of the "
    f"<span class='num'>{confirmed_count}</span> confirmed {collective} to leave "
    f"in the next 12 months. If retention worsens, the "
    f"<span class='num'>{plan['hire_gap']}</span>-person hire target grows with it."
    f"<br><br>"
    f"<strong>Data quality.</strong> "
    f"<span class='num'>{dq['pct_self_declared']}%</span> of skill records in the system "
    f"are self-declared or inferred, not verified by a manager. "
    f"The real \"confirmed\" number could be slightly lower once managers review."
)
st.markdown(
    f"<div class='risk-text'>{risk_paragraph}</div>",
    unsafe_allow_html=True,
)

dq = plan["data_quality"]
st.markdown(
    f"<div class='data-quality'>Data quality across all endorsements: "
    f"self-declared/inferred {dq['pct_self_declared']}%, "
    f"older than 2 years {dq['pct_stale']}%.</div>",
    unsafe_allow_html=True,
)


# ----- Chat panel -----------------------------------------------------------

st.markdown("<div class='section-h'>Ask</div>", unsafe_allow_html=True)

for msg in st.session_state["chat_history"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Who could we move from another team?")
if prompt:
    st.session_state["chat_history"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    answer = chat_response(prompt, plan, st.session_state["lookup"])
    st.session_state["chat_history"].append({"role": "assistant", "content": answer})
    with st.chat_message("assistant"):
        st.markdown(answer)

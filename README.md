# Workforce Plan

A briefing tool that turns a "we need 250 of role X by year Y" target into a defensible, costed action plan an executive can read in 90 seconds.

One scrollable page — defaults render on load; changing role, target, year, or budget recomputes the plan in place.

**Live demo:** deploy to [Streamlit Community Cloud](https://share.streamlit.io) — [instructions below](#deploy-streamlit-community-cloud). Add your app URL here once it's live.

**Repo:** [github.com/lassoregression/workforce-planning-agent](https://github.com/lassoregression/workforce-planning-agent)

---

## What this is for

A CHRO or business unit lead arrives at the start of a quarter with a target ("staff up to 250 AI Engineers by Q4 2027") and a budget ("we have $12M for this"). Today, that question gets answered by an analyst pulling spreadsheets from three systems: an HRIS for headcount, a learning platform for skill records, and a recruiting tool for hiring costs. The numbers come back two weeks later, often as a single recommendation ("we'll need to hire 250 people") with no visibility into who already has the skills, who is one course away, or how trustworthy the underlying data is.

This tool answers the same question in one screen, deterministically, with every number traceable to its source. The executive walks away with four things:

1. How many of the target are already in seat with verified skills, today
2. How many can be moved or reskilled internally before any external hiring starts
3. The financial difference between this plan and the naive "hire everyone externally" alternative
4. Which of those numbers are solid and which depend on data the company hasn't verified yet

## Why this problem and not a broader one

The move-vs-reskill-vs-hire decision is where organizations leak the most money. External hiring at a benchmark cost of around $45K per role is roughly 7x the cost of an internal move and 5x the cost of a reskill, and it routinely happens while qualified internal candidates sit in adjacent teams. The decision is narrow enough to model deterministically — four required skills per role, a few cost constants, a single time window — but consequential enough that getting it right shifts millions of dollars per quarter.

It also requires integrating three data domains that don't usually live in the same view: skills (the capability layer), workforce structure (who works where, who reports to whom), and finance (what each action costs and what the budget allows). The tool's value is the integration, not any single computation in isolation.

---

## Architecture

![Architecture diagram](diagram/architecture.svg)

Four files. Two of them are mock-data infrastructure; one is the engine that produces every number on screen; one is the user interface.

### `generate_data.py` — synthetic but intentionally messy data
Produces `workforce_data.json` with **200 employees** distributed across five job titles: AI Engineer (25), Data Engineer (50), Platform Engineer (40), Backend Engineer (50), Legacy System Admin (35). Random seed **42**, so re-running gives the same dataset.

The endorsement quality is deliberately uneven so the trust classifier has something real to do:

- About **40%** of endorsements are sourced as `self` or `inference` (untrusted)
- About **15%** are older than two years (stale)
- About **55%** of skills get a duplicate endorsement layered on top, often with a different (weaker) source — the same pattern you see in real SuccessFactors data where an employee self-declared a skill years ago and a manager later confirmed it
- ~10% of employees have no `flight_risk` recorded
- ~12% are "cross-trained" — they fully match the required skills for a role other than their current title, which is what makes the "movable from another team" bucket meaningful

The imperfections are the point. A clean synthetic dataset would let any classifier hit 100% accuracy and tell you nothing about how the system handles the real world.

### `engine.py` — deterministic core
This file contains every number the UI renders. No randomness, no LLM, no external calls. The functions are:

- `load_data()` — reads the JSON into a pandas DataFrame
- `is_endorsement_trusted(endorsement, current_date)` — the trust classifier
- `_classify(employee, required_skills, current_date)` — buckets a single employee
- `compute_plan(role, target_headcount, budget)` — the main entry point; returns a dict with 23 fields the UI consumes
- `employee_lookup()` — id → {name, job_title, department} for the chat fallback
- `people_for_action(action_kind, role, ids)` — for each action expander, builds a per-employee row with the action-specific context column ("Missing: ETL", "Weak signal on Java +2 more", etc.)
- `months_until(deadline, current_date)` — converts "2027 Q4" into months remaining

Constants in this file are the contract with the customer: `MOVE_COST = $6,000`, `RESKILL_COST = $8,000`, `HIRE_COST = $45,000`, `VERIFY_COST = $0`, `DEFAULT_FLIGHT_RISK = 0.15`, `CURRENT_DATE = "2026-06-20"`.

### `llm_utils.py` — the only place AI runs
Three public functions: `generate_headline`, `generate_risk`, `chat_response`. Each one tries the OpenAI API first (when `OPENAI_API_KEY` is set in the environment or `.env`) and falls back to a deterministic template if the call fails or no key is present. The fallbacks are not stubs — they are the production behavior when the API is unavailable. The model is `gpt-4o-mini` by default, overridable via `OPENAI_MODEL`.

### `app.py` — the Streamlit UI
Renders the whole page on first load with default values (AI Engineer, 250, 2027 Q4, $12M). No "Generate Plan" button. Changing any input recomputes the plan via `_recompute()` and rerenders. The page is a single scrollable document, not a multi-page app.

## Key design principle

The engine is fully deterministic. The LLM is used only for prose: the headline thesis sentence, the risk narrative, and chat replies. Swapping the model, downgrading it, or pulling the API key out entirely does not change a single number on the page. This matters because the executive is signing off on numbers, not on a model's confidence in the numbers. If the AI layer is unavailable, the page looks slightly less natural in two paragraphs and otherwise works exactly the same.

---

## How uncertainty is handled

The plan is built from imperfect data. Three sources of uncertainty are surfaced explicitly rather than smoothed over.

**Skill data quality.** The "Verify" action is the system's primary mechanism for owning this. People with the right skills on paper but only weak endorsements (self-declared, inferred, or stale beyond two years) sit in their own bucket called "Match on paper, need verification" rather than being silently included in the confirmed count or silently excluded. The footer of the risk section quantifies the global rate (`pct_self_declared` and `pct_stale` fields) so an executive can calibrate how much they trust the rest of the plan.

**Attrition.** The number is labeled "Attrition (1y)" in the gap row and "estimate" in the risk paragraph. It is computed as the sum of per-employee `flight_risk` scores across the confirmed pool, with `DEFAULT_FLIGHT_RISK = 0.15` filling in for anyone missing a score. This is an estimate, not a forecast — the risk section says so directly. A separate three-year erosion line (`confirmed_in_3yr = confirmed * (1 - avg_flight_risk)^3`) is shown beneath the gap table so the multi-year horizon isn't ignored.

**Timeline estimates.** The four action timelines (move 2 months, reskill 4, verify 1, hire 6) are hardcoded benchmark figures from `ACTION_MONTHS` in the engine. Each one is shown next to its breakdown right inline — for example, the hire row shows `~6 mo` next to `6 wk req approval + 12 wk pipeline + 4 wk start + 4 wk ramp`. The breakdown lives directly beside the headline number it justifies, so the executive can see how the figure was assembled without a click.

---

## Page anatomy

The sections in order, with what each one renders:

| # | Section | Contents | Render type |
|---|---|---|---|
| 1 | Eyebrow + thesis | Mono breadcrumb (`Workforce plan / AI Engineer / 250 by 2027 Q4`), Fraunces serif thesis sentence, Inter support paragraph with bold "Plan." prefix | Custom HTML |
| 2 | Inputs | Role selectbox, Target headcount number_input, Year selectbox (2027/2028/2029 Q4), Budget text_input that accepts `$12M`, `$500K`, `12,000,000`, etc. | Native Streamlit widgets |
| 3 | Who's available today | Lead sentence + 3-column data table (Category, Count, How we know) with confidence dots in green/amber/red | `<table class='data'>` |
| 4 | What it takes to reach _N_ | Summary sentence + 5-column gap table (Needed, Confirmed today, Attrition (1y), Developable, Hire gap) + 3-year erosion line | `<table class='gap'>` |
| 5 | Cost vs. hiring everyone | Savings figure rendered at 6rem in Fraunces serif, framed with two black hairlines. The page's typographic anchor. | Custom HTML |
| 6 | Show line items _(collapsed)_ | Itemized financial table | `<table class='data'>` inside an expander |
| 7 | Budget shortfall _(only when over budget)_ | Warning paragraph + radio with three options: prioritize internal actions (recommended), reduce target, escalate to CFO | `st.radio` |
| 8 | What we'll do, in sequence | Four action rows; each one has its own people-table expander immediately below it; each timing cell shows the headline month figure with the breakdown right beneath it | Per-action `<table class='data plan'>` blocks |
| 9 | What happens if we delay | Mono `[HIGH]/[MEDIUM]/[LOW]` pill in the section header (level derived from gap size and 3-year erosion), then two short paragraphs labeled **Attrition** and **Data quality** | Custom HTML |
| 10 | Ask | Streamlit chat input with placeholder "Who could we move from another team?" | `st.chat_input` + `st.chat_message` |

`st.metric` is not used anywhere — every numeric block is either custom HTML or a real `<table>`, so spacing and alignment match the rest of the document.

---

## Assumptions baked into the engine

These are choices the customer would tune, not laws of physics. They live in `engine.py` as module constants.

- **Required skills per role.** Four skills per role, hardcoded in `REQUIRED_SKILLS`. AI Engineer requires Python, MLOps, LLM Integration, System Design. Data Engineer requires Python, SQL, Spark, ETL. And so on for the other three.
- **Proficiency ≥ 3 (out of 5)** is the minimum to count toward the confirmed pool. Below 3 is treated as "has familiarity, not fluency."
- **Manager endorsements expire after 6 months.** After that they fall out of the trusted pool. Skills go stale and a manager who hasn't worked with someone recently can't speak to current capability with confidence.
- **Course completions are trusted for 2 years.** Longer than the manager window because a completed course is a fixed event with a verifiable artifact.
- **Self-declared and system-inferred skills are never trusted** without a manager or course endorsement on top. They surface employees into the "needs verification" bucket but never into "confirmed."
- **Action costs.** `$6K` per move, `$8K` per reskill, `$45K` per external hire, `$0` for verification (it's an internal manager conversation). These are benchmark figures; in a real deployment they would come from the customer's finance system or be set by the CFO.
- **Skills framework lives in SuccessFactors.** This prototype reads a JSON file, but the conceptual model is that `REQUIRED_SKILLS` is curated in the customer's instance and pulled via OData. If the framework isn't populated for a given role, this system would have no required-skills list to compare against, and the "needs verification" bucket would balloon — that's the data quality signal the customer should fix first.

## Bucketing logic

Every employee falls into exactly one of three buckets, checked in order. Order matters: the first match wins.

1. **Confirmed.** Has every required skill at proficiency 3+, AND every required skill has at least one trusted endorsement (manager within 6 months, OR course within 2 years) at proficiency 3+. This is the firm supply.
2. **One course away.** Missing exactly one required skill. Every other required skill is at proficiency 3+ AND trusted at that level. These are the reskill candidates — not "people we could maybe train," but "people who clear every bar on three of four skills and need one course on the fourth."
3. **Needs verification.** Has all required skills on paper at any proficiency, but at least one of them has only untrusted endorsements (self, inference, or stale). These are the people whose skill data is ambiguous; a manager conversation could move them into Confirmed and reduce the hire gap by one each.

Everyone else (missing two or more skills, or no required skills) is not counted toward this role at all.

## Plan math

Given the three buckets:

```
attrition         = round( sum(flight_risk) over confirmed,
                           default 0.15 when missing ),
                    capped at len(confirmed)

confirmed_in_3yr  = round( len(confirmed) * (1 - avg_flight_risk) ** 3 )

hire_gap          = max( 0,
                         target - (len(confirmed) - attrition)
                                - len(one_course_away) )

plan_cost         = len(movable_confirmed) * $6K
                  + len(one_course_away)   * $8K
                  + hire_gap               * $45K
                  + len(needs_verification) * $0

hire_all_cost     = target * $45K

savings           = hire_all_cost - plan_cost
```

When `plan_cost > budget`, three options are surfaced (option A is the recommended default: prioritize internal actions and defer hiring; option B reduces the target to what fits the budget; option C escalates the shortfall to the CFO). The hire gap is still computed and shown — the system never silently truncates the target to fit the wallet.

## Trade-offs that came up while building this

A short list of choices that could reasonably have gone the other way.

- **Capability over title** as the supply definition. The "holding the title" count is shown in the supply table, but it isn't the headline number. Title-based planning is what the tool is replacing.
- **Deterministic trust classifier** (a binary `is_endorsement_trusted` based on source and recency) over an ML confidence score. A numeric score would be more nuanced but harder to defend in a meeting with a CFO. "This endorsement is trusted because it's a manager endorsement from 4 months ago" is a sentence you can say out loud; "This endorsement scores 0.73" is not.
- **Engine is deterministic for every number** so the page can be reproduced exactly from the same data and inputs. Every chart, every count, every dollar amount comes from `engine.py`. The LLM only writes the prose. This is the single biggest design decision in the codebase.
- **No portfolio optimizer.** Given a budget, the system doesn't solve a knapsack to maximize headcount. It computes the natural-precedence plan (move first, then reskill, then hire), shows when that exceeds budget, and offers three sensible options. A real optimizer would be more clever but harder to explain, and the natural-precedence answer is right almost all the time.
- **No multi-role assignment.** A person who qualifies as both a Data Engineer and a Backend Engineer is counted in both supply pools when each role is computed. This is fine for a planning view but would need handling if the tool were used to assign actual people to actual reqs.
- **Honest prototype over a feature-rich demo.** The chat is a single-shot Q&A, not a multi-turn agent. The role list is hardcoded. There is no historical comparison, no scenario save, no PDF export. Each of those would be useful; none of them changes whether the core decision logic is right.
- **Rejected weighted scoring.** An earlier draft assigned a 0–100 readiness score per employee. It was indefensible — every weight choice felt arbitrary, and an executive would have rightly asked "why is verified-manager 0.6 and not 0.5?" The binary confirmed/verify split is simpler and easier to argue.
- **Inputs at the top, not in a sidebar.** A sidebar with toggles is the analyst-tool default; this is a briefing document. Defaults render on first load so the executive arrives at a plan, not a form.

## Roadmap

Concrete next steps for a production deployment — not aspirational features.

1. **Connect to SuccessFactors via OData.** Replace `load_data()` with a real call to `User`, `EmployeeSkills`, and `JobRequisition` entities. The schema in `workforce_data.json` is shaped to match what those entities actually return.
2. **Show endorsement provenance per employee.** In the people expanders, surface which specific endorsement is trusted vs flagged for each confirmed and ambiguous candidate, with the source, date, and proficiency. The data is already in the JSON; the UI just doesn't render it yet.
3. **Per-role action costs from finance.** `MOVE_COST`, `RESKILL_COST`, and `HIRE_COST` are benchmark figures right now. They should come from the customer's finance system or be set per role band by the CFO.
4. **Real attrition model.** Today's flight-risk score is a per-employee float with no provenance. A real deployment should pull from the customer's HRIS attrition prediction or fall back to a tenure-and-band-based heuristic, not assume the field is populated.
5. **Scenario save.** "Save this plan as the FY27 baseline" so the next read can show "vs. last quarter" deltas. Right now every load is independent.
6. **Multi-role planning.** When the user wants to staff three roles simultaneously (e.g. an AI initiative needing 50 AI Engineers, 30 Data Engineers, and 10 Platform Engineers), handle the case where a person qualifies for more than one of them and assign them to the role with the largest gap or shortest time-to-ready.
7. **Course catalog integration.** `COURSE_NAMES` is a hardcoded dict mapping role to a single course name. In production, "what's the course that closes the missing skill" should come from a learning system query, with cost and duration pulled live.

---

## Running it

```bash
cd workforce-planning-agent
pip install -r requirements.txt
python generate_data.py            # writes workforce_data.json (deterministic)
cp .env.example .env               # optional — enables LLM prose
streamlit run app.py
```

The app runs entirely offline. Copy `.env.example` to `.env` and set `OPENAI_API_KEY` (and optionally `OPENAI_MODEL`) to get LLM-generated headlines and risk paragraphs; without it, the deterministic templates take over and every number on the page stays identical.

## Deploy (Streamlit Community Cloud)

1. Push this repo to GitHub (public).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub, click **New app**.
3. Set **Main file path** to `app.py`. Leave **Branch** as `main`.
4. Deploy. No secrets required — the app runs on bundled `workforce_data.json` with deterministic prose fallbacks.
5. Optional: add `OPENAI_API_KEY` under **Settings → Secrets** for LLM-generated headlines and chat.
6. Update the live demo URL at the top of this README once you have it.

## License

MIT — see [LICENSE](LICENSE).

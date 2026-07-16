# Workforce Planning Agent

From workforce targets and budgets to defensible actions: **move, reskill, verify, or hire**.

[Open the live demo →](https://workforce-planning-agent.streamlit.app/)

This prototype turns a target role, headcount goal, deadline, and budget into an executive workforce briefing. It shows the internal capability already available, the remaining hiring gap, the cost and timing of each action, and how much confidence leaders should place in the underlying data.

It runs on synthetic data and works without an API key.

---

## The business problem

A CHRO or business-unit leader starts the quarter with a target:

> Staff 250 AI Engineers by Q4 2027 without exceeding a $12M budget.

That sounds like a headcount question. In practice, it is a decision problem spread across several systems:

- HRIS data says who works where;
- skill records suggest what each person can do;
- learning data shows who may be close to ready;
- recruiting benchmarks estimate the cost and time to hire; and
- finance defines what the organization can afford.

An analyst often has to reconcile those sources manually. The result arrives days or weeks later as a spreadsheet and, too often, a single hiring number. Leaders still cannot see who is already capable, who could move from another team, who is one course away, or which recommendations depend on unverified data.

The missing capability is not another workforce report. It is **decision support**: what should leaders do, why, what will it cost, and how much should they trust the answer?

## The focused decision

Workforce planning includes hiring, reskilling, redeployment, organization design, and long-term investment. This prototype deliberately tackles one narrow, high-value slice:

> For a target role, what mix of internal moves, targeted reskilling, skill verification, and external hiring should the organization pursue?

This scope is small enough to model transparently but meaningful enough to change a multimillion-dollar plan. It also exposes a common failure in title-based planning: qualified people may already exist elsewhere in the organization.

## What the prototype delivers

The app presents one scrollable executive briefing rather than a dashboard full of disconnected charts.

Given a role, target, deadline, and budget, it answers:

1. **Who is ready now?** Employees with every required skill supported by trusted evidence.
2. **Who can move internally?** Confirmed employees currently working in another role or team.
3. **Who is close enough to reskill?** Employees missing exactly one required skill.
4. **Who needs verification?** Employees who look qualified on paper but rely on self-declared, inferred, or stale evidence.
5. **What remains to hire?** The external gap after confirmed supply, expected attrition, and reskilling.
6. **What will it cost and how long will it take?** A sequenced action plan compared with an all-external-hiring baseline.

### Default scenario

For the bundled AI Engineer scenario—250 people by Q4 2027 with a $12M budget—the current synthetic dataset produces:

- **16** confirmed AI Engineers;
- **3** confirmed employees movable from other teams;
- **3** employees one course away;
- **1** employee requiring manager verification;
- **233** remaining external hires; and
- approximately **$723K in savings** versus hiring all 250 externally.

These figures are not claims about a real organization. They demonstrate how the decision model behaves when workforce evidence is incomplete and internal capability is distributed across teams.

## How the decision workflow works

### 1. Evaluate capability

Each employee is compared with four required skills for the selected role. Proficiency must be at least 3 out of 5.

### 2. Evaluate confidence

A skill counts as trusted only when it has:

- a manager endorsement from the last six months; or
- a course completion from the last two years.

Self-declared, system-inferred, and stale evidence can surface a potential match, but cannot silently turn that person into confirmed supply.

### 3. Map people to actions

Employees are classified in a strict order:

1. **Confirmed** — all required skills are present, proficient, and trusted.
2. **One course away** — exactly one required skill is missing; the rest are trusted.
3. **Needs verification** — all required skills appear in the record, but at least one lacks trusted evidence.
4. **Not counted** — two or more required skills are missing.

Confirmed employees outside the target role become internal-move candidates. The remaining gap becomes external hiring demand.

### 4. Build the plan

The engine applies a clear sequence:

1. retain confirmed supply;
2. move qualified people from other teams;
3. reskill employees who are one course away;
4. verify ambiguous records with managers; and
5. hire the remaining gap externally.

The result includes cost, time to staff, budget shortfall options, expected attrition, three-year supply erosion, and the quality of the evidence behind the recommendation.

## Why the recommendation is defensible

### The math is deterministic

Every count, cost, and savings figure comes from `engine.py`. The same inputs and workforce data always produce the same plan.

### AI explains; it does not decide

The optional LLM writes the headline, risk narrative, and chat response. It never classifies employees or calculates headcount, attrition, cost, or savings. If no API key is present, deterministic prose templates take over.

### Uncertainty remains visible

Weak evidence is not averaged into an opaque confidence score. It creates a concrete verification action. Leaders can see which part of the plan is firm and which part may change after manager review.

### Assumptions sit beside the recommendation

Action costs, time estimates, skill thresholds, endorsement windows, and attrition defaults are explicit. They can be challenged and replaced instead of hiding inside a model.

## Key product and technical trade-offs

- **Capability over title.** Job title remains visible, but verified capability determines supply. This reveals qualified employees in adjacent teams.

- **Rules over a weighted readiness score.** A score such as 73/100 appears precise but makes arbitrary weights difficult to defend. “Manager-verified four months ago” is easier to audit and discuss.

- **Deterministic decisions over AI decisioning.** Leaders are signing off on people and money. Model choice or API availability should not change the numerical recommendation.

- **Natural action order over portfolio optimization.** The prototype moves, reskills, and then hires. A mathematical optimizer could fit more actions into a budget, but would add complexity before the underlying assumptions have been validated.

- **One target role over premature breadth.** The current model avoids double-counting within a scenario. Simultaneous multi-role planning requires an allocation layer when the same person qualifies for several roles.

- **A briefing document over an analyst dashboard.** Defaults produce an immediate recommendation. Inputs refine the briefing in place instead of forcing the user through a wizard or a grid of filters.

- **An honest prototype over simulated completeness.** There is no scenario persistence, historical comparison, PDF export, or production integration. Those features matter only after the core decision logic earns trust.

## Architecture

![Workforce planning architecture](diagram/architecture.svg)

The prototype keeps data, decision logic, and explanation separate:

- **`generate_data.py`** creates a reproducible synthetic workforce.
- **`workforce_data.json`** stores employee, organization, skill, evidence, and risk records.
- **`engine.py`** produces every classification, action, cost, and risk number.
- **`llm_utils.py`** adds optional prose and provides deterministic fallbacks.
- **`app.py`** renders the Streamlit executive briefing.

The intended production boundary is straightforward: replace the JSON loader with governed HRIS, skills, learning, recruiting, and finance integrations while preserving the decision engine and its output contract.

### SuccessFactors-aligned future state

The data model is shaped around a plausible SAP SuccessFactors pattern:

- Employee Central for employee, role, department, and manager context;
- Talent Intelligence Hub or Growth Portfolio for skills and proficiency;
- learning records for course evidence;
- finance and workforce-demand inputs for cost and target constraints; and
- a separate attrition signal, since predicted flight risk is not native workforce truth.

The diagram distinguishes the working prototype path from future integrations.

## Synthetic data by design

The bundled dataset contains 200 synthetic employees across five technical roles. It is deterministic (`seed = 42`) but intentionally imperfect:

- self-declared and inferred endorsements;
- stale and duplicate evidence;
- missing flight-risk values;
- employees with partial skill matches; and
- cross-trained employees qualified outside their current role.

The imperfections are the point. A perfectly clean dataset would avoid the trust, provenance, and verification questions the product is meant to surface.

All names and workforce records are synthetic.

<details>
<summary><strong>Planning assumptions and formulas</strong></summary>

Current prototype defaults:

- Internal move: **$6,000** and approximately **2 months**
- Reskill: **$8,000** and approximately **4 months**
- Verification: **$0** and approximately **1 month**
- External hire: **$45,000** and approximately **6 months**
- Missing flight-risk value: **15%**

Core calculations:

```text
attrition = rounded sum of flight-risk values across confirmed supply

hire gap = target
           - confirmed supply
           + expected attrition
           - employees one course away

plan cost = internal moves × $6K
            + reskills × $8K
            + external hires × $45K

savings = cost of hiring the full target externally - plan cost
```

Verification is shown as upside but is not automatically subtracted from the hire gap. A manager must first confirm the evidence.

These values are prototype assumptions, not universal benchmarks. A production deployment should source them by role, geography, and level.

</details>

## Run locally

Requires Python 3.11+.

```bash
git clone https://github.com/lassoregression/workforce-planning-agent.git
cd workforce-planning-agent

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

streamlit run app.py
```

The generated dataset is already included. To reproduce it:

```bash
python generate_data.py
```

### Optional LLM features

The app works without an API key. To enable generated prose and chat:

```bash
cp .env.example .env
```

Then set:

```text
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o-mini
```

No model output is used in workforce classification or plan math.

## Prototype limits

- Plans one target role at a time.
- Does not allocate the same employee across simultaneous role targets.
- Uses fixed benchmark costs and timelines.
- Treats synthetic flight-risk values as estimates, not forecasts.
- Does not persist scenarios or compare them over time.
- Provides single-turn chat grounded in the current plan.

## Roadmap

The path from prototype to a customer-ready pilot is intentionally incremental:

1. **Validate** — test classification and confidence rules with managers and staffing outcomes.
2. **Integrate** — connect governed HR, skills, learning, recruiting, and finance sources.
3. **Close the verification loop** — record manager decisions and improve evidence quality.
4. **Expand** — add simultaneous multi-role allocation once single-role recommendations are trusted.
5. **Track outcomes** — measure adoption, cost impact, time to staff, verification rate, and data quality.
6. **Broaden scenarios** — add organization-design and workforce-investment decisions after the core workflow is proven.

## License

MIT © 2026 Mujeeb Khan ([lassoregression](https://github.com/lassoregression)). See [LICENSE](LICENSE).

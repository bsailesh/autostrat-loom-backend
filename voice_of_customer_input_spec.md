# Agent 1 — Voice of Customer: input specification

## Why this agent's input problem is different

Market Insights works on a free-text product line, because markets are publicly
discussed. Tech & Regulation needs a scoping envelope, because regulation is
public but applicability is not.

**Voice of Customer needs the evidence itself.** Customer voice is mostly not
public. Without customer data this agent cannot produce a sentiment score, rank
pain points by frequency, validate a persona, or state why a deal was lost — and
the honest response is to say so rather than to produce thin versions of each.

So the input has two parts, and they do different jobs:

| Part | What it is | What it does |
|---|---|---|
| **Customer context** | Structured fields — segments, channels, products, named customers | Tells the agent who the customers are, so public evidence and uploaded documents can be attributed |
| **Evidence** | Uploaded documents and, later, connected systems | The customer voice itself. Without it, most of this agent's analyses are unavailable |

Context without evidence produces an **external customer-context analysis** —
real, useful, and not a voice of customer analysis. The output must say which it
is, in the first line, every time.

---

## Part 1 — Customer context

Structured, form-based, roughly fifteen minutes. Required for attribution.

### 1.1 Customer segments

```
segment_key, segment_name, description, approximate_count
OEM-PRIME,   Prime contractors,    Airframe and missile primes buying at shipset level,  6
OEM-TIER1,   Tier 1 integrators,   System integrators specifying actuation,              14
MRO,         MRO and sustainment,  Depot and field maintenance organisations,            30
OPERATOR,    End operators,        Fleet operators with direct influence on spec,        unknown
```

`approximate_count` may be `unknown`. An honest unknown is better than a guess,
and the agent will say when a finding rests on a segment whose size is unstated.

**Scopes:** who findings are attributed to. All evidence is reported by segment
or role, never by named customer, unless §1.5 permits otherwise.

**Without it:** findings cannot be grouped, and frequency means nothing — ten
complaints from one operator and ten from ten primes are different findings.

### 1.2 Products

Reuses the product categories from the Tech & Regulation envelope where both
agents are configured. See Part 5.

```
category_key, category_name
EMA-FIN,   Missile fin actuation
EMA-TVC,   Thrust vector control
EMA-UTIL,  Utility actuation
```

**Scopes:** which product a piece of feedback is about.

### 1.3 Channels

How the customer reaches their customers, and how feedback arrives.

```
channel, direction, note
Direct sales,            inbound and outbound,  Primes and Tier 1
Distributor,             outbound,              Utility actuation aftermarket
Field service,           inbound,               Primary source of failure reports
Programme reviews,       both,                  Quarterly with primes
```

**Scopes:** where feedback originates, and which channels are unrepresented in
the evidence supplied — which is itself a finding.

### 1.4 Named customers, optional

```
customer_name, segment_key, products, relationship_status
```

**Optional and sensitive.** Used only for attribution inside the system. See
§1.5 for how it appears in output.

### 1.5 Attribution policy

One setting, three values:

| Value | Output behaviour |
|---|---|
| `segment_only` (default) | "Three Tier 1 integrators report…" Never a customer name |
| `role_and_segment` | "A programme manager at a Tier 1 integrator reports…" |
| `named` | Customers named directly. Only where the customer confirms this is permitted |

**Default is `segment_only`.** A single-source finding is Low confidence
regardless of how emphatically it was stated, and the agent says so.

### 1.6 Known pain points, optional

What the customer already believes their customers complain about.

```
pain_point, segment_key, product, their_assessment
```

**This is deliberately a hypothesis, not evidence.** The agent tests it against
whatever evidence exists and reports three outcomes separately: corroborated,
contradicted, or not found in the evidence base. **A contradicted belief is the
single most valuable thing this agent can produce**, and it is unavailable
unless the belief is stated up front.

---

## Part 2 — Evidence

### 2.1 Document upload — available now

Documents, not form fields. Each upload declares its type, because type
determines which analyses it enables.

| Document type | Enables |
|---|---|
| Support tickets | Pain point frequency, trend direction |
| Warranty claims | Failure-driven pain points, cost impact |
| Service and field reports | Operational pain points, environment-specific findings |
| Survey responses and verbatims | Sentiment scoring, theme extraction |
| NPS detail | Sentiment, with segment attribution where present |
| Win/loss reports | Win/loss rationale, competitive gaps |
| Customer visit and interview notes | Persona validation, decision drivers |
| Call centre logs | Pain point frequency, language customers actually use |
| Meeting minutes and programme reviews | Priorities as stated by the customer |
| Dealer and distributor feedback | Channel-specific findings |
| Product reviews, public | Sentiment, lower confidence than first-party |
| Field investigation reports | Root-cause findings |

Per upload: type, `as_of` date, period covered, segment coverage if known, and
whether it is complete or a sample. **A sample is not a census** — the agent
must not report frequency from a sample as though it were.

### 2.2 Connected systems — planned, not yet available

The input screen shows these as **planned**, clearly labelled. They are not
implemented and must not be presented as present-but-inactive.

| System | What it would supply | Status |
|---|---|---|
| Salesforce | Opportunities, win/loss, contacts, activity notes | Planned |
| Dynamics 365 | As above | Planned |
| Zendesk / ServiceNow | Support tickets, resolution times | Planned |
| SharePoint | Visit reports, programme reviews, meeting minutes | Planned |
| Qualtrics / Medallia | Survey responses, NPS | Planned |
| Fleet telemetry | Operational data, usage patterns | Planned |

**Do not render these as greyed-out buttons.** A connector that looks present
and does nothing contradicts the thing this platform is built on — that it
states what it does not know. Label the section "Planned integrations" and say
what each would add.

The honest framing is also the better one commercially: these are the gaps that
make the case for an integration conversation, and naming them is how that
conversation starts.

---

## Part 3 — Operating tier

Stated in the first line of every run.

### Tier 2 only — no customer evidence

**Available:** external forces and STEEP analysis, emerging trends from public
sources, competitor feature comparison from public disclosure, market-level
demand evidence, segment structure from public sources, SWOT from public
evidence.

**Not available, and stated as such:**

- Sentiment scores — nothing to score
- Pain points ranked by frequency — no counts exist
- Validated personas — **persona hypotheses to validate** are produced instead,
  labelled, each with the question that would confirm or refute it
- Feature request frequency
- Win/loss rationale
- Segment-specific problem clustering
- Any test of the §1.6 known pain points

Output is an **external customer-context analysis**. Name it that way in the
report title, not only in the body.

### Tier 1 partial

Each analysis enabled by its specific source. State per analysis which source
enabled it and which are still missing.

### Tier 1 substantial

Full analysis. Public evidence used for external forces and competitive context
only.

---

## Part 4 — Degradation

The run is never blocked. Each absence has a stated consequence.

| Missing | Consequence stated in output |
|---|---|
| Segments | Findings cannot be grouped or attributed; frequency is meaningless |
| Products | Feedback cannot be attached to a product line |
| Channels | Cannot identify which feedback routes are unrepresented |
| Known pain points | No corroboration or contradiction testing — the highest-value analysis is unavailable |
| **All evidence documents** | **Tier 2 run. Sentiment, frequency, personas and win/loss unavailable. The single most consequential omission** |
| Ticket or claim data | Pain points reported unranked |
| Survey or verbatim data | Qualitative themes only; no sentiment score |
| Win/loss reports | No win/loss rationale |
| Visit or interview notes | Persona hypotheses rather than validated personas |

---

## Part 5 — Shared with other agents

| Field | VoC | Tech & Reg | Sustainment |
|---|---|---|---|
| Product categories | yes | yes | yes |
| Customer segments | yes | no | no |
| Channels | yes | no | partially |
| Platforms | no | yes | yes |
| Supplier watch list | no | yes | yes |

**Product categories are the second field to appear in two agents' inputs** —
Tech & Regulation already declares them. Where both are configured, VoC should
read Tech & Regulation's categories rather than asking twice, with its own
additions allowed.

This is the point at which a shared **Product Profile** stops being premature.
Two agents now need the same list, a third will. Worth extracting after this
agent ships, not during.

---

## Part 6 — Worked example: Arden Actuation Systems

**Segments:** prime contractors (6); Tier 1 integrators (14); MRO and
sustainment (30); end operators (unknown).

**Products:** the five categories from the Tech & Regulation envelope.

**Channels:** direct sales to primes and Tier 1; distributor for utility
actuation aftermarket; field service, inbound; quarterly programme reviews.

**Attribution:** `segment_only`.

**Known pain points, to be tested:**

- *Primes say our lead times are the longest in the qualified set* — procurement
- *Integrators find our control interface harder to integrate than Moog's* —
  engineering
- *MRO organisations say field diagnosis takes too long without a service tool*
  — sustainment

**Evidence supplied:** none at demo time. This is deliberate — the Tier 2 run
shows what the agent produces from public evidence alone, and the gap between
that and a Tier 1 run is the integration conversation.

Note what the known pain points do even in a Tier 2 run: each is reported as
**not corroborated in the evidence base, because no customer evidence was
supplied** — which names precisely what a document upload or a CRM connection
would settle. A belief the customer holds, which the system cannot yet test, is
a sharper argument for connecting data than any feature list.

---

## Open questions

1. **Does a contradicted belief become candidate work?** Tech & Regulation emits
   candidate work for Agent 5. A contradicted assumption is arguably a finding
   rather than a piece of work. Suggest: no candidate work from VoC in v1, but
   decide deliberately
2. **Sample versus census.** The agent must not report frequency from a sample
   as a census. Is `is_sample` enough, or does it need a sampling description?
3. **Document volume.** Support ticket exports can be very large. The 414MB
   instance summarises upstream reports above 150K characters; evidence
   documents need a similar rule, and summarising customer verbatims loses
   exactly the language that makes them valuable
4. **Attribution policy enforcement.** `segment_only` is a prompt instruction
   today. Should names be stripped before the model sees them?

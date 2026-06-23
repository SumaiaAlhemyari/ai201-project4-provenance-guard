# Provenance Guard — Planning Document

## Architecture Narrative

A user submits a piece of text via POST /submit. The text passes through
two independent detection signals: an LLM-based classifier (Groq) that
reads the text semantically, and a stylometric analyzer that measures
statistical writing patterns. Both signals return a score between 0 and 1,
where 1 means "very likely AI-generated." These scores are combined into
a single confidence score. That score maps to one of three transparency
labels shown to the user. Every decision is written to an audit log.
If a creator believes they were misclassified, they submit a POST /appeal
with their content_id and reasoning. The system updates the status to
"under_review" and logs the appeal.

## Architecture Diagram

### Submission Flow

POST /submit
    → Signal 1: Groq LLM Score (0–1)
    → Signal 2: Stylometric Score (0–1)
    → Confidence Scorer: combines both → single score (0–1)
    → Label Generator: score → label text
    → Audit Log: writes full entry
    → Response: {content_id, attribution, confidence, label}

### Appeal Flow

POST /appeal
    → Lookup content_id in storage
    → Update status to "under_review"
    → Audit Log: appends appeal entry
    → Response: {message: "Appeal received", content_id}

## Detection Signals

### Signal 1: LLM-Based Classification (Groq)
- **What it measures:** Whether the text reads as semantically and
  stylistically consistent with AI-generated writing — things like
  overly smooth transitions, generic phrasing, balanced sentence rhythm.
- **Output:** A float between 0 and 1 (1 = very likely AI)
- **What it misses:** Highly polished human writing that mimics AI tone;
  AI text that has been heavily edited by a human.

### Signal 2: Stylometric Heuristics (Pure Python)
- **What it measures:** Statistical properties of the writing —
  sentence length variance, type-token ratio (vocabulary diversity),
  and punctuation density. AI writing tends to be more uniform;
  human writing more variable.
- **Output:** A float between 0 and 1 (1 = very likely AI)
- **What it misses:** Human writers who naturally write in a uniform,
  clean style (e.g. technical writers, non-native English speakers).

## Confidence Scoring

Both signals are weighted equally and averaged:
  combined_score = (llm_score * 0.6) + (stylometric_score * 0.4)

Groq gets slightly more weight (0.6) because it captures meaning,
not just surface statistics.

Thresholds:
- 0.00 – 0.35 → "likely_human"
- 0.36 – 0.64 → "uncertain"
- 0.65 – 1.00 → "likely_ai"

## Transparency Labels

### High-confidence AI (score 0.65–1.0):
"⚠️ Our system found patterns consistent with AI-generated text.
This content has been flagged for review. If you are the creator
and believe this is an error, you may submit an appeal."

### Uncertain (score 0.36–0.64):
"🔍 Our system could not confidently determine whether this content
was human-written or AI-generated. It has been marked as uncertain.
Creators may submit an appeal to provide additional context."

### High-confidence Human (score 0.00–0.35):
"✅ Our system found patterns consistent with human-written content.
This content has been attributed to the creator."

## Appeals Workflow

- Any creator can submit an appeal using their content_id.
- They must provide a creator_reasoning field explaining why they
  believe the classification is wrong.
- On receipt: status is updated to "under_review" in storage,
  the appeal reasoning is added to the audit log entry.
- No automated re-classification occurs — a human reviewer
  would handle it manually.

## Edge Cases

1. **Non-native English speakers:** Writers who use simpler vocabulary
   and more uniform sentence structures may score high on stylometrics
   even though they are human. This is a known false-positive risk.

2. **Heavily quoted or list-based content:** Blog posts with bullet
   points or heavy use of quotes will have unusual sentence length
   variance that may confuse the stylometric signal.

## API Endpoints

| Method | Endpoint  | Accepts                        | Returns                                      |
|--------|-----------|--------------------------------|----------------------------------------------|
| POST   | /submit   | {text, creator_id}             | {content_id, attribution, confidence, label} |
| POST   | /appeal   | {content_id, creator_reasoning}| {message, content_id}                        |
| GET    | /log      | —                              | {entries: [...]}                             |

## Rate Limiting

Limit: 10 requests per minute, 100 per day per IP address.

Reasoning: A real writer submitting their own work would rarely
submit more than a few pieces per hour. 10/minute is generous for
legitimate use but stops automated flooding. 100/day covers
heavy users without enabling bulk abuse.

## AI Tool Plan

This section explains how I will use AI tools (like Claude) to help me
build each milestone. For each milestone I describe: what I will give
the AI, what I will ask it to build, and how I will check that what
it built actually works before moving on.

---

### M3 — Building the Flask App + First Detection Signal

**What I'll give the AI:**
- The Architecture Diagram from this document
- The Detection Signals section from this document

**What I'll ask it to build:**
- The basic Flask app file (app.py) with a POST /submit route that
  accepts text and creator_id
- A function that sends text to the Groq API and gets back a score
  between 0 and 1 indicating how likely the text is AI-generated

**How I'll verify it works:**
- I'll run the Groq function on its own with 3 test sentences before
  connecting it to the Flask app
- I'll send a test request to POST /submit using curl and confirm I
  get back a JSON response with content_id, attribution, confidence,
  and label fields

---

### M4 — Adding the Second Signal + Combining Scores

**What I'll give the AI:**
- The Detection Signals section from this document
- The Confidence Scoring section from this document
- The Architecture Diagram from this document

**What I'll ask it to build:**
- A function that analyzes the writing style of the text (sentence
  length, vocabulary variety, punctuation) and returns a score
  between 0 and 1
- A scoring function that takes both signal scores and combines them
  into one final confidence score using the weights I defined

**How I'll verify it works:**
- I'll test with 4 specific inputs: one clearly AI, one clearly human,
  and two in-between cases
- I'll check that the clearly AI text scores noticeably higher than
  the clearly human text
- If they don't differ enough, I'll look at each signal score
  separately to find which one is off

---

### M5 — Adding Labels, Appeals, Rate Limiting, and Audit Log

**What I'll give the AI:**
- The Transparency Labels section from this document
- The Appeals Workflow section from this document
- The Architecture Diagram from this document

**What I'll ask it to build:**
- A function that takes the confidence score and returns the correct
  label text (one of three variants I wrote above)
- The POST /appeal endpoint that accepts content_id and
  creator_reasoning, updates the status, and logs the appeal

**How I'll verify it works:**
- I'll submit three different texts that I expect to land in each
  label range and confirm each one returns the right label text
- I'll submit an appeal using a content_id from an earlier submission,
  then check GET /log to confirm the status changed to "under_review"
  and the reasoning was saved
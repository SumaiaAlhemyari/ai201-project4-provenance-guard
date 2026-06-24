# Provenance Guard

A backend system that classifies submitted text as human-written or
AI-generated, scores confidence in that classification, surfaces a
transparency label to users, and handles appeals from creators who
believe they've been misclassified.

---

## Architecture Overview

A piece of text travels through the system like this:

1. Creator submits text via POST /submit
2. Signal 1 (Groq LLM) reads the text and returns a score (0–1)
3. Signal 2 (Stylometric heuristics) measures writing patterns and returns a score (0–1)
4. Confidence Scorer combines both scores into one number (0–1)
5. Label Generator maps that number to one of three plain-English labels
6. Audit Log saves every decision with full detail
7. Response is returned to the user with: content_id, attribution, confidence, label

If a creator wants to contest a classification:

1. Creator submits POST /appeal with their content_id and reasoning
2. System updates that content's status to "under_review"
3. Audit Log is updated with the appeal reasoning
4. Confirmation is returned to the creator
Submission Flow:

POST /submit

→ Groq LLM Score (0–1)

→ Stylometric Score (0–1)

→ Confidence Score (weighted average)

→ Transparency Label (one of three variants)

→ Audit Log entry written

→ Response returned
Appeal Flow:

POST /appeal

→ Look up content_id

→ Update status to "under_review"

→ Audit Log updated

→ Confirmation returned

---

## API Endpoints

| Method | Endpoint | Accepts | Returns |
|--------|----------|---------|---------|
| POST | /submit | `{text, creator_id}` | `{content_id, attribution, confidence, label}` |
| POST | /appeal | `{content_id, creator_reasoning}` | `{message, content_id}` |
| GET | /log | — | `{entries: [...]}` |

---

## Detection Signals

### Signal 1: LLM-Based Classification (Groq)

**What it measures:** Whether the text reads as semantically consistent
with AI-generated writing — things like overly smooth transitions,
generic phrasing, and balanced sentence rhythm. The Groq model
(llama-3.3-70b-versatile) is prompted to return a single score
between 0 and 1.

**Why I chose it:** An LLM understands meaning and context, not just
surface statistics. It catches things like generic conclusions and
corporate-sounding language that stylometric heuristics would miss.

**What it misses:** Highly polished human writing that naturally
sounds formal. A well-edited essay might score higher than it should.

---

### Signal 2: Stylometric Heuristics (Pure Python)

**What it measures:** Three statistical properties of the writing:
- Sentence length variance (AI text is more uniform)
- Type-token ratio (AI text uses less varied vocabulary)
- Punctuation density (AI text uses punctuation more consistently)

**Why I chose it:** These metrics are completely independent from the
LLM signal — one is semantic, one is structural. Combining them gives
a more complete picture than either alone.

**What it misses:** Human writers who naturally write in a clean,
uniform style — technical writers, non-native English speakers, or
writers following strict style guides may score higher than they should.

---

## Confidence Scoring

Both signals are combined using a weighted average:
confidence = (llm_score × 0.6) + (stylometric_score × 0.4)

Groq gets slightly more weight (0.6) because it captures meaning and
context, which is harder to fake than surface statistics.

**Thresholds:**
- 0.00 – 0.35 → likely_human
- 0.36 – 0.64 → uncertain
- 0.65 – 1.00 → likely_ai

**How I validated the scores are meaningful:**

I tested four deliberately different inputs and confirmed the scores
matched my intuition:

| Text | LLM Score | Stylometric Score | Confidence | Attribution |
|------|-----------|-------------------|------------|-------------|
| Casual ramen rant | low | low | 0.1263 | likely_human |
| Sunset on porch | low | medium | 0.3611 | uncertain |
| Paradigm shift paragraph | medium | medium | 0.5924 | uncertain |
| Business buzzword paragraph | high | high | 0.6688 | likely_ai |

The system is intentionally cautious — it only flags content as
likely_ai when both signals agree strongly. This reflects the project's
guidance that a false positive (labeling a human's work as AI) is worse
than a false negative.

---

## Transparency Labels

### High-confidence AI (confidence 0.65–1.0):
"⚠️ Our system found patterns consistent with AI-generated text.
This content has been flagged for review. If you are the creator
and believe this is an error, you may submit an appeal."

### Uncertain (confidence 0.36–0.64):
"🔍 Our system could not confidently determine whether this content
was human-written or AI-generated. It has been marked as uncertain.
Creators may submit an appeal to provide additional context."

### High-confidence Human (confidence 0.00–0.35):
"✅ Our system found patterns consistent with human-written content.
This content has been attributed to the creator."

---

## Rate Limiting

**Limits:** 10 requests per minute, 100 requests per day per IP address.

**Reasoning:** A real writer submitting their own work would rarely
submit more than a few pieces per session. 10 per minute is generous
for legitimate use — someone could submit 10 poems in a minute if they
wanted to. But it stops automated scripts from flooding the system with
hundreds of requests. 100 per day covers even the heaviest legitimate
users without enabling bulk abuse. When the limit is hit, the server
returns a 429 status code.

---

## Known Limitations

**Non-native English speakers:**
A writer who uses simpler vocabulary and more uniform sentence structures
will score higher on the stylometric signal even if they are completely
human. This is a direct consequence of how the type-token ratio and
sentence length variance metrics work — they measure uniformity, not
humanity. A non-native speaker writing carefully and formally could
easily land in the "uncertain" or even "likely_ai" range. The appeals
workflow exists specifically to handle this case.

**Short text submissions:**
Both signals perform poorly on very short texts (under 3–4 sentences).
The stylometric signal explicitly returns a neutral 0.5 score when
there aren't enough sentences to measure variance. A one-line poem
or a short caption will produce unreliable results.

---

## Spec Reflection

**One way the spec helped:**
Writing out the three label variants in planning.md before writing
any code forced me to decide what the thresholds meant to a real user
before making them a technical decision. When I implemented the
get_label() function, I already had the exact text ready — I didn't
have to figure out the UX and the code at the same time.

**One way implementation diverged from the spec:**
In planning.md I assumed the stylometric score would be a reliable
second signal on its own. In practice, it tends to score most text
as moderately AI-like (0.5–0.7) regardless of how obviously human
the writing is, because it's sensitive to formal punctuation and
vocabulary. The LLM signal ended up doing more of the heavy lifting
than I originally planned. If I were deploying this for real, I would
recalibrate the stylometric weights or replace it with a more
discriminating signal.

---

## AI Usage

### Instance 1: Generating the Flask app skeleton and Groq signal
I provided Claude with my architecture diagram and detection signals
section from planning.md and asked it to generate the Flask app
skeleton with a POST /submit route and the Groq signal function.
It produced a working structure but the prompt it used for Groq was
too open-ended — it asked the model to "assess" the text without
specifying the output format. I revised the prompt to explicitly
require a single number between 0.0 and 1.0 with no explanation,
which made the response reliable and parseable.

### Instance 2: Generating the stylometric signal
I asked Claude to implement the stylometric heuristics function based
on my spec's description of sentence length variance, type-token ratio,
and punctuation density. The generated function was correct but used
a variance normalization ceiling of 100, which made the variance_score
almost always close to 1.0 for real text. I revised the ceiling to 50,
which produced more meaningful spread across different writing samples.

---

## Setup Instructions

1. Clone this repository
2. Create a virtual environment: `python -m venv .venv`
3. Activate it (Windows): `.venv\Scripts\activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Create a `.env` file with your Groq API key: `GROQ_API_KEY=your_key_here`
6. Run the app: `python app.py`
7. The server runs at `http://localhost:5000`

## Requirements

- Python 3.8+
- Groq API key (free tier)
- See requirements.txt for Python packages
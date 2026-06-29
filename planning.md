# Provenance Guard
## Project Planning Document

---

### Project Overview

Provenance Guard is a backend API designed for creative sharing
platforms. Its purpose is to analyze submitted text and classify
it as human-written or AI-generated, without forcing a binary
verdict. The system returns a confidence score, a plain-English
transparency label, and provides a mechanism for creators to
contest classifications they believe are incorrect.

The system is built around three principles:

1. Honest uncertainty: a score of 0.51 and a score of 0.95 must
   produce meaningfully different responses
2. Creator fairness: a false positive (labeling human work as AI)
   is treated as worse than a false negative
3. Auditability: every decision is logged in full, including
   appeals

---

### File Structure

The project is organized into three files, each with one
clearly defined responsibility:
app.py          Flask server and all 3 API routes

detection.py    Both signals, confidence scoring, and labels

store.py        Audit log and content storage

ui.py           Gradio web interface (connects to Flask API)

Separation rationale:

- app.py has no detection logic
- detection.py has no knowledge of Flask or storage
- store.py has no knowledge of Flask or detection
- ui.py communicates with Flask only through HTTP requests

---

### Architecture

#### Submission Flow
POST /submit  (app.py)

|

v

get_llm_score(text)

Groq LLM returns a score between 0 and 1     (detection.py)

|

v

get_stylometric_score(text)

Measures sentence variance, vocabulary

diversity, and punctuation density           (detection.py)

|

v

get_confidence_score(llm, stylo)

Combines both scores into one number         (detection.py)

|

v

get_label(confidence)

Maps score to one of three label variants    (detection.py)

|

v

save_content() + write_log_entry()

Stores result and writes audit entry         (store.py)

|

v

Response: {content_id, attribution,

confidence, label}

#### Appeal Flow
POST /appeal  (app.py)

|

v

get_content(content_id)

Verifies submission exists                   (store.py)

|

v

update_content_status("under_review")

Updates content store                        (store.py)

|

v

Updates matching audit log entry

Adds appeal_reasoning to the record         (store.py)

|

v

Response: {message, content_id}

---

### Detection Signals

#### Signal 1: LLM-Based Classification

File: detection.py, function: get_llm_score()

What it measures:
The Groq LLM (llama-3.3-70b-versatile) reads the text and
assesses whether it exhibits semantic patterns associated with
AI-generated writing. This includes overly smooth transitions,
generic phrasing, balanced sentence rhythm, and formulaic
structure such as "it is important to note" or "in conclusion."

Output format:
A single float between 0.0 and 1.0.
0.0 = very likely human-written
1.0 = very likely AI-generated

Why this signal:
An LLM understands meaning and context, not just surface
statistics. It catches patterns that stylometric analysis
cannot, such as generic conclusions, corporate-sounding
language, and unnaturally coherent argumentation.

Blind spot:
Highly polished human writing that is formal in tone may
score higher than expected. A carefully edited academic essay
could trigger a moderate LLM score despite being human-written.

Error handling:
If Groq returns an unexpected response or the API fails,
the function returns a neutral score of 0.5 rather than
crashing the system.

---

#### Signal 2: Stylometric Heuristics

File: detection.py, function: get_stylometric_score()

What it measures:
Three statistical properties of the text that differ between
human and AI writing:

Metric 1 - Sentence length variance:
AI text tends to use sentences of similar length throughout.
Human writing is more irregular. Low variance produces a
higher score (more AI-like).

Metric 2 - Type-token ratio (vocabulary diversity):
Calculated as unique words divided by total words. AI text
tends to be more repetitive in vocabulary. A lower ratio
produces a higher score (more AI-like).

Metric 3 - Punctuation density:
Calculated as punctuation characters divided by total
characters. AI text tends to use punctuation more
consistently. Higher density produces a higher score.

Output format:
A single float between 0.0 and 1.0, rounded to 4 decimal
places. Returns 0.5 (neutral) if fewer than 2 sentences
are detected.

Why this signal:
These metrics are structurally independent from the LLM
signal. One measures meaning, one measures form. Combining
them produces a more complete picture than either alone.

Blind spot:
Non-native English speakers and technical writers naturally
produce more uniform text. A non-native speaker writing
carefully in formal English could score high on stylometrics
despite being the genuine author.

---

### Confidence Scoring

#### Original Specification

Both signals combined using a weighted average:
confidence = (llm_score x 0.6) + (stylometric_score x 0.4)

Original thresholds:
0.00 to 0.35   likely_human

0.36 to 0.64   uncertain

0.65 to 1.00   likely_ai

Groq was given higher weight (0.6) because it captures
semantic meaning, which is harder to replicate than surface
statistics.

#### Calibration Update After Testing

During testing with 6 deliberate test cases (2 clearly human,
2 clearly AI, 2 borderline), the stylometric signal consistently
underscored AI text, dragging the combined score below the
likely_ai threshold even when Groq correctly identified the
text as AI-generated.

Adjustment made:
confidence = (llm_score x 0.7) + (stylometric_score x 0.3)

Updated thresholds:
0.00 to 0.35   likely_human

0.36 to 0.59   uncertain

0.60 to 1.00   likely_ai

Rationale for adjustment:
The stylometric signal is a useful supporting signal but
not a reliable primary detector. Increasing Groq weight
to 0.7 and lowering the likely_ai threshold to 0.60 produced
correct classifications across all 6 test cases while keeping
the system appropriately cautious about false positives.

What a score of 0.60 means:
The system has moderate-to-high confidence the text is
AI-generated. At least one signal scored strongly and the
other scored at or above neutral. This is enough to flag
for review but not enough to be certain.

What a score of 0.35 means:
Both signals scored low. The text exhibits variable sentence
length, diverse vocabulary, and irregular punctuation. The
system attributes this to human authorship.

What a score of 0.50 means:
The signals disagree or both returned near-neutral scores.
The system cannot determine authorship. The uncertain label
is shown and the creator may appeal.

---

### Transparency Labels

Three label variants are defined in detection.py,
function: get_label(confidence).

The label text was finalized before implementation and
has not changed.

#### High-Confidence AI (score 0.60 to 1.0)

Attribution value: likely_ai

Label text:
"Our system found patterns consistent with AI-generated
text. This content has been flagged for review. If you
are the creator and believe this is an error, you may
submit an appeal."

#### Uncertain (score 0.36 to 0.59)

Attribution value: uncertain

Label text:
"Our system could not confidently determine whether this
content was human-written or AI-generated. It has been
marked as uncertain. Creators may submit an appeal to
provide additional context."

#### High-Confidence Human (score 0.00 to 0.35)

Attribution value: likely_human

Label text:
"Our system found patterns consistent with human-written
content. This content has been attributed to the creator."

Design note:
The likely_ai label explicitly mentions the appeal option
because false positives are the highest-stakes outcome on
a creative platform. A human creator who is incorrectly
flagged needs a clear path forward.

---

### Appeals Workflow

#### Who can submit an appeal

Any creator can submit an appeal for any content that has
been classified. No authentication is required in this
implementation. The only requirement is a valid content_id.

#### What the creator provides

The creator submits a content_id and a creator_reasoning
field explaining why they believe the classification is
incorrect. The content_id is generated automatically by
the system and passed silently through the interface.
The creator never needs to find or copy it manually.

#### What the system does

On receiving a valid appeal:

1. The content_id is verified against the content store
2. The status field is updated from "classified" to
   "under_review" in the content store
3. The matching audit log entry is updated with the
   appeal_reasoning and the new status
4. A confirmation message is returned to the creator

Automated re-classification does not occur. A human
reviewer would examine the audit log entry, read the
creator reasoning, and make a final determination.

#### What a reviewer sees in the audit log

Each log entry after an appeal contains:
content_id:        ABC123

creator_id:        XYZ789

timestamp:         2026-06-25T18:30:00Z

attribution:       likely_ai

confidence:        0.67

llm_score:         0.80

stylometric_score: 0.42

status:            under_review

appeal_reasoning:  "I wrote this myself for a business

class. English is my second language

and my professor encouraged formal

vocabulary."

---

### Anticipated Edge Cases

#### Edge Case 1: Non-native English speakers

A creator who writes carefully in formal English, using
simple vocabulary and uniform sentence structure, will
score higher on the stylometric signal than a native
speaker writing casually. This is a direct consequence
of how the type-token ratio and sentence length variance
metrics work. They measure uniformity, not humanity.

Example scenario: a non-native English speaker submitting
a formal essay for a writing platform could land in the
uncertain or likely_ai range despite being the genuine
author. This is the primary false-positive risk in the
system. The appeals workflow exists specifically for
this case.

#### Edge Case 2: Short text submissions

Both signals perform poorly on texts under 3 to 4
sentences. The stylometric function explicitly returns
a neutral score of 0.5 when fewer than 2 sentences are
detected. A one-line poem, a short caption, or a brief
bio will produce unreliable results from both signals.

The system does not currently reject short submissions
or warn the user. This is a known gap. A minimum text
length validation would reduce unreliable classifications.

---

### API Endpoints
Method   Endpoint   Accepts                       Returns

POST     /submit    {text, creator_id}            {content_id, attribution,

confidence, label}

POST     /appeal    {content_id,                  {message, content_id}

creator_reasoning}

GET      /log       none                          {entries: [...]}

---

### Rate Limiting

Applied to: POST /submit only
Limits: 10 requests per minute, 100 requests per day per IP

Reasoning:
A creator submitting their own work would rarely need more
than a few submissions per session. 10 per minute is
generous for legitimate use while blocking automated
flooding. 100 per day accommodates heavy users without
enabling bulk abuse. Rate limit violations return HTTP 429.

---

### AI Tool Plan

This section documents how AI assistance was used across
the three implementation milestones. For each milestone,
it records what was provided to the AI, what was requested,
and how the output was verified before use.

#### Milestone 3: Submission Endpoint and Signal 1

Provided to AI:
- Architecture diagram from this document
- Detection signals section from this document

Requested from AI:
- Flask app skeleton with POST /submit route stub
- Groq signal function returning a float between 0 and 1

Verification steps:
- Groq function tested independently on 3 inputs before
  being connected to the route
- POST /submit tested with curl to confirm response
  includes content_id, attribution, confidence, and label

What was revised:
The Groq prompt generated by the AI was too open-ended.
It asked the model to "assess" the text without specifying
output format. The prompt was revised to require a single
number between 0.0 and 1.0 with no explanation, making
the response consistently parseable.

#### Milestone 4: Second Signal and Confidence Scoring

Provided to AI:
- Detection signals section from this document
- Confidence scoring section from this document
- Architecture diagram from this document

Requested from AI:
- Stylometric heuristics function
- Confidence scoring function combining both signals

Verification steps:
- Stylometric function tested independently before
  integration
- 4 test inputs used: clearly AI, clearly human, and
  two borderline cases
- Individual signal scores examined separately when
  combined scores seemed off

What was revised:
The generated stylometric function used a variance
normalization ceiling of 100, which produced scores
clustered near 1.0 for most real text. The ceiling was
revised to 50, producing more meaningful spread across
different writing samples.

#### Milestone 5: Production Layer

Provided to AI:
- Transparency labels section from this document
- Appeals workflow section from this document
- Architecture diagram from this document

Requested from AI:
- Label generation function mapping confidence to label text
- POST /appeal endpoint
- Storage functions in store.py

Verification steps:
- All 3 label variants confirmed reachable using test inputs
- Appeal submitted using a real content_id and verified
  in GET /log output
- Rate limiting tested by sending 12 rapid requests,
  confirming 429 responses after request 10
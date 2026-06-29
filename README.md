# Provenance Guard

Provenance Guard is a backend API for creative sharing platforms.
It analyzes submitted text and classifies it as human-written or
AI-generated, without forcing a binary verdict. The system returns
a confidence score and a plain-English transparency label that
reflects genuine uncertainty. Creators who believe they have been
misclassified can submit an appeal through a dedicated workflow.

The system is built around one core principle: a false positive,
labeling a human creator's work as AI-generated, is a more serious
failure than a false negative. Every design decision reflects
this asymmetry.

---

## Project Structure

The codebase is organized into three backend files and one
interface file, each with a single clearly defined responsibility.
app.py          Flask server and all 3 API routes

detection.py    Both signals, confidence scoring, and labels

store.py        Audit log and content storage

ui.py           Gradio web interface

Separation rationale:

- app.py contains no detection logic
- detection.py has no knowledge of Flask or storage
- store.py has no knowledge of Flask or detection
- ui.py communicates with the backend only through HTTP requests

---

## Architecture Overview

### Submission Flow

A creator submits text through the Gradio interface or directly
via the API. The request is received by POST /submit in app.py
and passes through the following steps:
POST /submit  (app.py)

|

v

get_llm_score(text)

Groq LLM reads the text and returns a score       (detection.py)

|

v

get_stylometric_score(text)

Measures sentence variance, vocabulary

diversity, and punctuation density                 (detection.py)

|

v

get_confidence_score(llm, stylo)

Combines both scores into one number              (detection.py)

|

v

get_label(confidence)

Maps score to one of three label variants         (detection.py)

|

v

save_content() and write_log_entry()

Stores result and writes structured audit entry   (store.py)

|

v

Response returned:

{content_id, attribution, confidence, label}

### Appeal Flow

A creator submits a POST /appeal request with their content_id
and reasoning. The system does not re-classify automatically.
A human reviewer examines the audit log entry and makes a
final determination.
POST /appeal  (app.py)

|

v

get_content(content_id)

Verifies the submission exists                    (store.py)

|

v

update_content_status("under_review")

Updates the content store                         (store.py)

|

v

Audit log entry updated with

appeal_reasoning and new status                   (store.py)

|

v

Response returned:

{message, content_id}

---

## API Endpoints
Method   Endpoint   Accepts                        Returns

POST     /submit    {text, creator_id}             {content_id, attribution,

confidence, label}
POST     /appeal    {content_id,                   {message, content_id}

creator_reasoning}
GET      /log       none                           {entries: [...]}

---

## Detection Signals

### Signal 1: LLM-Based Classification (Groq)

File: detection.py, function: get_llm_score()

**What it measures:**
The Groq LLM (llama-3.3-70b-versatile) reads the submitted
text and assesses whether it exhibits semantic patterns
associated with AI-generated writing. This includes overly
smooth transitions, generic phrasing, balanced sentence rhythm,
and formulaic structures such as "it is important to note"
or "in conclusion, it is evident that."

**Output:** A float between 0.0 and 1.0.
0.0 = very likely human-written.
1.0 = very likely AI-generated.

**Why this signal was chosen:**
An LLM understands meaning and context, not just surface
statistics. It detects patterns that stylometric analysis
cannot, such as generic argumentation, corporate-sounding
language, and unnaturally coherent structure.

**What it misses:**
Highly polished human writing that is formal in tone may
score higher than expected. A carefully edited academic essay
or a formal business letter could receive a moderate LLM
score despite being entirely human-written.

**Error handling:**
If Groq returns an unexpected response or the API call fails,
the function returns a neutral score of 0.5 rather than
crashing the system.

---

### Signal 2: Stylometric Heuristics (Pure Python)

File: detection.py, function: get_stylometric_score()

**What it measures:**
Three statistical properties of the text that differ
between human and AI writing:

Metric 1: Sentence length variance.
AI text tends to use sentences of similar length. Human
writing is more irregular. Low variance produces a higher
score (more AI-like).

Metric 2: Type-token ratio (vocabulary diversity).
Calculated as unique words divided by total words. AI text
tends to repeat vocabulary more than human writing. A lower
ratio produces a higher score (more AI-like).

Metric 3: Punctuation density.
Calculated as punctuation characters divided by total
characters. AI text tends to use punctuation more
consistently. Higher density produces a higher score.

**Output:** A float between 0.0 and 1.0, rounded to 4
decimal places. Returns 0.5 (neutral) if fewer than 2
sentences are detected.

**Why this signal was chosen:**
These metrics are structurally independent from the LLM
signal. One measures meaning, one measures form. Combining
genuinely independent signals produces a more reliable
result than running two variations of the same approach.

**What it misses:**
Non-native English speakers and technical writers naturally
produce more uniform text. A non-native speaker writing
carefully in formal English may score high on stylometrics
despite being the genuine author. This is the primary
false-positive risk in the system.

---

## Confidence Scoring

Both signals are combined using a weighted average.

### Original Specification
confidence = (llm_score x 0.6) + (stylometric_score x 0.4)

Original thresholds:
0.00 to 0.35   likely_human

0.36 to 0.64   uncertain

0.65 to 1.00   likely_ai

Groq was assigned higher weight (0.6) because semantic
understanding is more informative than surface statistics
for this classification task.

### Calibration Update After Testing

During testing with 6 deliberate test cases (2 clearly human,
2 clearly AI, 2 borderline), the stylometric signal
consistently underscored AI text. This dragged the combined
score below the likely_ai threshold even when Groq correctly
identified the text as AI-generated.

The following adjustment was made:
confidence = (llm_score x 0.7) + (stylometric_score x 0.3)

Updated thresholds:
0.00 to 0.35   likely_human

0.36 to 0.59   uncertain

0.60 to 1.00   likely_ai

Rationale: The stylometric signal is a useful supporting
signal but not a reliable primary detector on its own.
Increasing Groq weight to 0.7 and lowering the likely_ai
threshold to 0.60 produced correct classifications across
all 6 test cases while keeping the system appropriately
cautious about false positives.

### Validation Results

Six test inputs were used to confirm scores were meaningful:
Text Type                    Confidence   Attribution

Casual ramen rant (human)    0.13         likely_human

Personal story (human)       0.18         likely_human

Formal academic (borderline) 0.42         uncertain

Lightly edited AI (border.)  0.55         uncertain

Generic essay conclusion      0.67         likely_ai

Corporate leadership text     0.71         likely_ai

---

## Transparency Labels

Three label variants are implemented in detection.py,
function: get_label(confidence). The label text was
finalized before implementation and has not changed.

### High-Confidence AI (score 0.60 to 1.0)

Attribution value: likely_ai

Label text:
"Our system found patterns consistent with AI-generated
text. This content has been flagged for review. If you
are the creator and believe this is an error, you may
submit an appeal."

### Uncertain (score 0.36 to 0.59)

Attribution value: uncertain

Label text:
"Our system could not confidently determine whether this
content was human-written or AI-generated. It has been
marked as uncertain. Creators may submit an appeal to
provide additional context."

### High-Confidence Human (score 0.00 to 0.35)

Attribution value: likely_human

Label text:
"Our system found patterns consistent with human-written
content. This content has been attributed to the creator."

Design note:
The likely_ai label explicitly mentions the appeal option
because a human creator who is incorrectly flagged needs
a clear and immediate path forward.

---

## Rate Limiting

Applied to: POST /submit only.
Limits: 10 requests per minute, 100 requests per day per IP.

Reasoning:
A creator submitting their own work would rarely need more
than a few submissions per session. 10 per minute is generous
for legitimate use while preventing automated scripts from
flooding the system. 100 per day accommodates heavy users
without enabling bulk abuse. Rate limit violations return
HTTP 429. The limit was verified by sending 12 rapid requests
and confirming 429 responses after request 10.

---

## Known Limitations

### Limitation 1: Non-native English speakers

A creator who writes carefully in formal English, using
simple vocabulary and uniform sentence structure, will score
higher on the stylometric signal than a native speaker
writing casually. The type-token ratio and sentence length
variance metrics measure uniformity, not humanity.

A non-native speaker submitting a formal essay could land
in the uncertain or likely_ai range despite being the
genuine author. This is a direct consequence of how the
stylometric signal is constructed, not a calibration issue
that can be resolved by adjusting weights. The appeals
workflow exists specifically to address this scenario.

### Limitation 2: Short text submissions

Both signals produce unreliable results on texts under 3
to 4 sentences. The stylometric function returns a neutral
score of 0.5 when fewer than 2 sentences are detected.
A one-line poem, a short caption, or a brief bio will
not be classified reliably by either signal.

The system does not currently reject short submissions or
warn the creator. A minimum text length validation would
reduce the frequency of unreliable classifications on
short creative work.

---

## Spec Reflection

### One way the spec helped

Writing out the three label variants in planning.md before
writing any code forced a decision about what each threshold
meant to a real user before it became a technical choice.
When get_label() was implemented in detection.py, the exact
label text was already defined. The UX decision and the
engineering decision did not have to happen at the same time.

### One way implementation diverged from the spec

The original spec assigned equal reliability to both signals
with a 60/40 weight split. In practice, the stylometric
signal consistently underperformed on AI text, scoring most
inputs as moderately AI-like regardless of actual authorship.
The LLM signal carried more of the classification work than
originally planned. The weights were adjusted to 70/30 and
the likely_ai threshold was lowered from 0.65 to 0.60 based
on test results. If this system were deployed in production,
the stylometric signal would need to be replaced with a more
discriminating structural analysis method.

---

## AI Usage

### Instance 1: Groq signal function and Flask skeleton

The AI tool was provided the architecture diagram and
detection signals section from planning.md. It was asked
to generate the Flask app skeleton with a POST /submit
route and the Groq signal function.

The generated Groq prompt was too open-ended. It instructed
the model to "assess" the text without specifying the output
format. The prompt was revised to require a single number
between 0.0 and 1.0 with no explanation or surrounding text.
This made the response consistently parseable and prevented
runtime errors caused by the model returning sentences
instead of numbers.

### Instance 2: Stylometric signal function

The AI tool was provided the detection signals section and
asked to implement the stylometric heuristics function
covering sentence length variance, type-token ratio, and
punctuation density.

The generated function used a variance normalization ceiling
of 100, which caused the variance_score to cluster near 1.0
for almost all real text inputs. The ceiling was revised to
50, which produced a more meaningful distribution of scores
across different writing samples and allowed the metric to
distinguish between uniform and variable writing more
effectively.

---

## Setup and Running the Project

### Requirements
Python 3.8 or higher

Groq API key (free tier)

### Installation

Step 1: Clone the repository.

Step 2: Create and activate a virtual environment.
python -m venv .venv

.venv\Scripts\activate        (Windows)

source .venv/bin/activate     (Mac and Linux)

Step 3: Install dependencies.
pip install -r requirements.txt

Step 4: Create a .env file in the project root.
GROQ_API_KEY=your_key_here

### Running the System

Two terminals are required. Both must be running at the
same time.

Terminal 1: Start the Flask backend.
python app.py

The backend runs at http://127.0.0.1:5000

Terminal 2: Start the Gradio interface.
python ui.py

The interface opens at http://127.0.0.1:7860

### Testing the API Directly (Windows PowerShell)

Submit text for analysis:

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:5000/submit `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"text": "your text here", "creator_id": "test-user"}' `
  | Select-Object -Expand Content
```

View the audit log:

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:5000/log `
  | Select-Object -Expand Content
```

Test rate limiting (sends 12 requests, expects 429 after 10):

```powershell
for ($i=1; $i -le 12; $i++) {
  try {
    $r = Invoke-WebRequest -Uri http://127.0.0.1:5000/submit `
      -Method POST `
      -ContentType "application/json" `
      -Body '{"text": "Rate limit test.", "creator_id": "test"}'
    Write-Host "Request $i: 200"
  } catch {
    Write-Host "Request $i: 429"
  }
}
```
# app.py
# ─────────────────────────────────────────────────────────────
# This file is the entry point of the application.
# Its only jobs are:
#   - Create the Flask app
#   - Set up rate limiting
#   - Define the 3 routes (/submit, /appeal, /log)
#
# It imports detection logic from detection.py
# It imports data functions from store.py
# ─────────────────────────────────────────────────────────────

import uuid
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from detection import (
    get_llm_score,
    get_stylometric_score,
    get_confidence_score,
    get_label,
)
from store import (
    write_log_entry,
    get_log,
    save_content,
    get_content,
    update_content_status,
    audit_log,
)

# ── Create the Flask app ───────────────────────────────────────
app = Flask(__name__)

# ── Set up rate limiting ───────────────────────────────────────
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)


# ══════════════════════════════════════════════════════════════
#  ROUTE 1: POST /submit
# ══════════════════════════════════════════════════════════════

@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    """
    Accepts a piece of text for attribution analysis.
    Returns: content_id, attribution, confidence, label
    """
    data = request.get_json()

    # Validate required fields
    if not data or "text" not in data or "creator_id" not in data:
        return jsonify({
            "error": "Missing required fields: text, creator_id"
        }), 400

    text = data["text"]
    creator_id = data["creator_id"]

    # Generate a unique ID for this submission
    content_id = str(uuid.uuid4())

    # Run both detection signals
    llm_score = get_llm_score(text)
    stylometric_score = get_stylometric_score(text)

    # Combine into one confidence score
    confidence = get_confidence_score(llm_score, stylometric_score)

    # Generate the transparency label
    attribution, label = get_label(confidence)

    # Save to content store
    save_content(content_id, {
        "content_id": content_id,
        "creator_id": creator_id,
        "text": text,
        "attribution": attribution,
        "confidence": confidence,
        "status": "classified",
    })

    # Write to audit log
    write_log_entry({
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "attribution": attribution,
        "confidence": confidence,
        "llm_score": llm_score,
        "stylometric_score": stylometric_score,
        "status": "classified",
        "appeal_reasoning": None,
    })

    return jsonify({
        "content_id": content_id,
        "attribution": attribution,
        "confidence": confidence,
        "label": label,
    })


# ══════════════════════════════════════════════════════════════
#  ROUTE 2: POST /appeal
# ══════════════════════════════════════════════════════════════

@app.route("/appeal", methods=["POST"])
def appeal():
    """
    Accepts an appeal from a creator who believes they were
    misclassified.
    Requires: content_id, creator_reasoning
    """
    data = request.get_json()

    # Validate required fields
    if not data or "content_id" not in data or "creator_reasoning" not in data:
        return jsonify({
            "error": "Missing required fields: content_id, creator_reasoning"
        }), 400

    content_id = data["content_id"]
    reasoning = data["creator_reasoning"]

    # Check that this content_id exists
    content = get_content(content_id)
    if content is None:
        return jsonify({"error": "content_id not found"}), 404

    # Update status in content store
    update_content_status(content_id, "under_review")

    # Update the matching audit log entry
    for entry in audit_log:
        if entry["content_id"] == content_id:
            entry["status"] = "under_review"
            entry["appeal_reasoning"] = reasoning
            break

    return jsonify({
        "message": "Appeal received. Your content has been marked as under review.",
        "content_id": content_id,
    })


# ══════════════════════════════════════════════════════════════
#  ROUTE 3: GET /log
# ══════════════════════════════════════════════════════════════

@app.route("/log", methods=["GET"])
def log():
    """
    Returns all audit log entries as JSON.
    """
    return jsonify({"entries": get_log()})


# ══════════════════════════════════════════════════════════════
#  RUN THE APP
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app.run(debug=True)
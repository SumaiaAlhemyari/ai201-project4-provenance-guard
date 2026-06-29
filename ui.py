# ui.py
# ─────────────────────────────────────────────────────────────
# Gradio interface for Provenance Guard.
# Talks to the Flask API running at http://127.0.0.1:5000
# Run with: python ui.py
#
# Design decisions:
# - Creator ID is auto-generated silently (6 characters)
# - Content ID is returned as 6 characters from Flask
# - Appeal section only appears after a submission is made
# - Content ID is passed to appeal automatically, never shown
# - analyze_btn is wired only once to avoid double API calls
# ─────────────────────────────────────────────────────────────

import uuid
import requests
import gradio as gr

API = "http://127.0.0.1:5000"


# ══════════════════════════════════════════════════════════════
#  HELPER: Generate a short 6-character ID
# ══════════════════════════════════════════════════════════════

def short_id():
    """Generates a random 6-character alphanumeric ID."""
    return str(uuid.uuid4()).replace("-", "")[:6].upper()


# ══════════════════════════════════════════════════════════════
#  FUNCTION 1: Submit content
# ══════════════════════════════════════════════════════════════

def submit_content(text):
    """
    Sends text to the Flask /submit endpoint.
    Creator ID is generated automatically and never shown.
    Returns attribution, confidence, label, content_id,
    and reveals the appeal section.
    """
    if not text.strip():
        return (
            "❌ Please enter some text to analyze.",
            "",
            "",
            "",
            gr.update(visible=False),
        )

    creator_id = short_id()

    try:
        response = requests.post(
            f"{API}/submit",
            json={"text": text, "creator_id": creator_id},
        )
        data = response.json()

        if response.status_code != 200:
            return (
                f"❌ Error: {data.get('error', 'Something went wrong.')}",
                "",
                "",
                "",
                gr.update(visible=False),
            )

        attribution = data["attribution"].replace("_", " ").upper()
        confidence  = str(data["confidence"])
        label       = data["label"]
        content_id  = data["content_id"]

        # Reveal the appeal section now that we have a result
        return (
            attribution,
            confidence,
            label,
            content_id,
            gr.update(visible=True),
        )

    except requests.exceptions.ConnectionError:
        return (
            "❌ Could not reach the server. Make sure Flask is running.",
            "",
            "",
            "",
            gr.update(visible=False),
        )


# ══════════════════════════════════════════════════════════════
#  FUNCTION 2: Submit appeal
# ══════════════════════════════════════════════════════════════

def submit_appeal(content_id, reasoning):
    """
    Sends an appeal to the Flask /appeal endpoint.
    Content ID is passed silently from the hidden store.
    """
    if not content_id.strip():
        return "❌ No Content ID found. Please submit some content first."
    if not reasoning.strip():
        return "❌ Please enter your reasoning."

    try:
        response = requests.post(
            f"{API}/appeal",
            json={"content_id": content_id, "creator_reasoning": reasoning},
        )
        data = response.json()

        if response.status_code != 200:
            return f"❌ Error: {data.get('error', 'Something went wrong.')}"

        return f"✅ {data['message']}"

    except requests.exceptions.ConnectionError:
        return "❌ Could not reach the server. Make sure Flask is running."


# ══════════════════════════════════════════════════════════════
#  FUNCTION 3: Load audit log
# ══════════════════════════════════════════════════════════════

def load_log():
    """
    Fetches all audit log entries from the Flask /log endpoint
    and formats them for display.
    """
    try:
        response = requests.get(f"{API}/log")
        data = response.json()
        entries = data.get("entries", [])

        if not entries:
            return "No entries yet. Submit some content first."

        output = ""
        for entry in reversed(entries):
            output += "─" * 60 + "\n"
            output += f"content_id:         {entry['content_id']}\n"
            output += f"creator_id:         {entry['creator_id']}\n"
            output += f"timestamp:          {entry['timestamp']}\n"
            output += f"attribution:        {entry['attribution']}\n"
            output += f"confidence:         {entry['confidence']}\n"
            output += f"llm_score:          {entry['llm_score']}\n"
            output += f"stylometric_score:  {entry['stylometric_score']}\n"
            output += f"status:             {entry['status']}\n"
            output += f"appeal_reasoning:   {entry['appeal_reasoning'] or 'none'}\n"
            output += "\n"

        return output

    except requests.exceptions.ConnectionError:
        return "❌ Could not reach the server. Make sure Flask is running."


# ══════════════════════════════════════════════════════════════
#  BUILD THE INTERFACE
# ══════════════════════════════════════════════════════════════

with gr.Blocks(title="Provenance Guard") as app:

    gr.Markdown("# 🛡️ Provenance Guard")
    gr.Markdown("AI content attribution · confidence scoring · appeals workflow")
    gr.Markdown("---")

    # ── Section 1: Submit ──────────────────────────────────────
    gr.Markdown("## Submit Content")
    gr.Markdown(
        "Paste a piece of text to analyze whether it was written "
        "by a human or generated by AI."
    )

    text_input = gr.Textbox(
        label="Text to analyze",
        placeholder="Paste a poem, story excerpt, or blog post here...",
        lines=5,
    )

    analyze_btn = gr.Button("Analyze", variant="primary")

    with gr.Row():
        attribution_output = gr.Textbox(
            label="Attribution",
            interactive=False,
        )
        confidence_output = gr.Textbox(
            label="Confidence Score",
            interactive=False,
        )

    label_output = gr.Textbox(
        label="Transparency Label",
        interactive=False,
        lines=3,
    )

    # Hidden field — stores content_id silently between sections
    content_id_store = gr.Textbox(
        value="",
        visible=False,
    )

    gr.Markdown("---")

    # ── Section 2: Appeal ──────────────────────────────────────
    # Hidden until a submission is made
    with gr.Group(visible=False) as appeal_section:

        gr.Markdown("## Submit an Appeal")
        gr.Markdown(
            "If you believe your content was misclassified, "
            "explain your reasoning below and click Submit Appeal."
        )

        appeal_reason_input = gr.Textbox(
            label="Your reasoning",
            placeholder="Explain why you believe the classification is incorrect...",
            lines=4,
        )

        appeal_btn = gr.Button("Submit Appeal", variant="primary")
        appeal_output = gr.Textbox(label="Appeal Status", interactive=False)

        appeal_btn.click(
            fn=submit_appeal,
            inputs=[content_id_store, appeal_reason_input],
            outputs=[appeal_output],
        )

    # Wire analyze button ONCE — outputs include appeal_section
    analyze_btn.click(
        fn=submit_content,
        inputs=[text_input],
        outputs=[
            attribution_output,
            confidence_output,
            label_output,
            content_id_store,
            appeal_section,
        ],
    )

    gr.Markdown("---")

    # ── Section 3: Audit Log ───────────────────────────────────
    gr.Markdown("## Audit Log")
    gr.Markdown("Shows all submissions and appeals. Click Refresh to update.")

    refresh_btn = gr.Button("Refresh Log")
    log_output = gr.Textbox(
        label="Log Entries",
        interactive=False,
        lines=20,
    )

    refresh_btn.click(
        fn=load_log,
        inputs=[],
        outputs=[log_output],
    )


# ── Run ────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.launch()
# store.py
# ─────────────────────────────────────────────────────────────
# This file is the single source of truth for all data in the
# system. Any file that needs to read or write data imports
# from here. Nothing else in the project stores data.
# ─────────────────────────────────────────────────────────────


# Holds every audit log entry as a list of dictionaries.
# Each entry represents one submission or appeal.
audit_log = []


# Holds the current state of every submitted piece of content.
# Key: content_id (string)
# Value: dictionary with content details and current status
content_store = {}


def write_log_entry(entry):
    """
    Adds a new entry to the audit log.
    Called every time a submission or appeal comes in.
    """
    audit_log.append(entry)


def get_log():
    """
    Returns all audit log entries.
    Used by the GET /log route.
    """
    return audit_log


def save_content(content_id, data):
    """
    Saves a new submission to the content store.
    Called when a new piece of text is submitted.
    """
    content_store[content_id] = data


def get_content(content_id):
    """
    Looks up a submission by its content_id.
    Returns the content data or None if not found.
    """
    return content_store.get(content_id, None)


def update_content_status(content_id, status):
    """
    Updates the status of a submission.
    Called when an appeal is received.
    """
    if content_id in content_store:
        content_store[content_id]["status"] = status
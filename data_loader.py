"""
data_loader.py

This file reads all our email JSON files and turns them into ONE simple,
common format. Each file we made earlier looks a bit different
(different field names, different categories), so this file is the
"translator" that makes them all look the same before the rest of the
agent works with them.

Why this matters: in a real system, emails come from Gmail's API, which
has its own format. This loader is where that translation would happen
too - so this file is a stand-in for "the part that talks to Gmail".
"""

import json
import os

# Categories from our different mock files all get mapped to one
# common list of categories, so the rest of the agent only needs to
# know about these names.
CATEGORY_MAP = {
    "subscription": "subscription",
    "deal": "deal",
    "discount": "deal",          # main_inbox calls these "discount", we treat them the same as "deal"
    "needs_reply": "needs_reply",
    "personal": "needs_reply",   # personal messages are treated like "needs a reply" too
    "noise": "noise",
    "job_application": "job_application",
    "ticket_purchase": "ticket_purchase",
    "challenge": "challenge",
}

# Categories that actually need a YES/NO decision from the user
# (cancel/keep, reply/ignore, act/ignore). Everything else is just
# informational and shown in the dashboard without asking anything.
DECISION_REQUIRED_CATEGORIES = {"subscription", "deal", "needs_reply"}


def load_json_file(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # subscriptions.json is a plain list, university/clutter/main files might be too,
    # but some of our earlier experiments wrapped things in a dict - handle both safely.
    if isinstance(data, dict) and "emails" in data:
        return data["emails"]
    return data


def normalize_email(raw, source_file):
    """
    Take one raw email (in whatever shape its source file used) and
    return a clean, common-shape email dictionary.
    """
    raw_category = raw.get("category", "noise")
    clean_category = CATEGORY_MAP.get(raw_category, "noise")

    account = raw.get("account")
    vendor_or_sender = raw.get("vendor") or raw.get("from") or raw.get("from_email")

    # "decision_key" is what we use later to remember a decision.
    # This needs to be different depending on the category:
    #
    # - subscription / deal: keyed on (vendor + account) together.
    #   This is on purpose - the SAME company in two different accounts
    #   (e.g. Netflix on your personal AND work email) must be treated
    #   as two separate decisions, otherwise cancelling one would
    #   wrongly also cancel the other in the agent's memory.
    #
    # - needs_reply: keyed on the email's own unique id, NOT the
    #   sender. This is also on purpose - ignoring one message from
    #   a person should not silently ignore every future message from
    #   them too. Each new message from a person is its own decision.
    if clean_category in ("subscription", "deal"):
        decision_key = f"{vendor_or_sender}::{account}"
    elif clean_category == "needs_reply":
        decision_key = raw.get("id")
    else:
        decision_key = vendor_or_sender

    return {
        "id": raw.get("id"),
        "account": account,
        "from_email": raw.get("from") or raw.get("from_email"),
        "from_name": raw.get("from_name"),
        "subject": raw.get("subject"),
        "timestamp": raw.get("timestamp"),
        "body": raw.get("body"),
        "attachments": raw.get("attachments", []),
        "category": clean_category,
        "requires_decision": clean_category in DECISION_REQUIRED_CATEGORIES,
        "decision_key": decision_key,
        "source_file": source_file,
        "thread_history": raw.get("thread_history", []),

    }


def load_all_emails(data_folder):
    """
    Loads every .json file in the data folder and returns one big list
    of normalized emails, sorted by time (oldest first).
    """
    all_emails = []
    for filename in sorted(os.listdir(data_folder)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(data_folder, filename)
        raw_emails = load_json_file(path)
        for raw in raw_emails:
            all_emails.append(normalize_email(raw, filename))

    all_emails.sort(key=lambda e: e["timestamp"])
    return all_emails


if __name__ == "__main__":
    emails = load_all_emails(os.path.join(os.path.dirname(__file__), "data"))
    print(f"Loaded {len(emails)} emails total")
    from collections import Counter
    print(Counter(e["category"] for e in emails))

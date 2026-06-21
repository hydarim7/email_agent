"""
view_decisions.py

Shows every decision you've made so far, in a readable way - not just
raw keys, but matched back to the actual subject/sender they belong to.

Run it with:
    python view_decisions.py
"""

import os

import data_loader
import state_store


def main():
    decisions = state_store.load_decisions()

    if not decisions:
        print("No decisions saved yet.")
        return

    data_folder = os.path.join(os.path.dirname(__file__), "data")
    all_emails = data_loader.load_all_emails(data_folder)

    # Build a lookup so we can match a decision_key back to a real email
    by_key = {}
    for email in all_emails:
        by_key.setdefault(email["decision_key"], []).append(email)

    print(f"You have {len(decisions)} saved decision(s):\n")

    for key, decision in decisions.items():
        matches = by_key.get(key, [])
        if matches:
            example = matches[0]
            label = f"[{example['category']}] '{example['subject']}' from {example['from_name']} ({example['account']})"
        else:
            label = f"(no matching email found for key: {key})"

        print(f"- {label}")
        print(f"  -> decision: {decision}\n")


if __name__ == "__main__":
    main()

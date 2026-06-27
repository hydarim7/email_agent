"""
pipeline.py

This is the main agent loop. Each time you run it, it does exactly
what we drew in the diagram earlier:

  1. Find NEW emails (since the last checkpoint, per account)
  2. Look at the PENDING list (old items still waiting for a decision)
  3. For each item that needs a decision:
       - if we already have a saved decision for it -> resolve it
         automatically (no question asked again)
       - if not -> add it to the pending list (it will show up next
         time too, until the user decides)
  4. Save the new checkpoint, so next run only looks at what's new
     after this point.

In a real build, step "classify the email" would call an LLM/agent
(built with ADK). Here, since our mock data already has the correct
category written into it, we use that directly - this lets us test
the whole pipeline logic (memory, checkpoint, pending list) without
needing an API key. The classify_email() function below is the one
spot you'd swap in a real agent call later.
"""

import os
import time
from datetime import datetime, timezone

import data_loader
import state_store
import ai_classifier
import action_agent

MIN_TIMESTAMP = "0001-01-01T00:00:00Z"  # used as "the beginning of time" for first run

# In REAL AI mode, never process more than this many emails in one run -
# this keeps us safely under a tight daily quota (as low as 20/day on
# some free accounts). Anything left over simply isn't checkpointed
# yet, so it shows up again as "new" on the next run, picking up right
# where we left off.
MAX_AI_EMAILS_PER_RUN = 5


def fake_draft_text(email_like, decision):
    """
    A simple, non-AI template draft - used in TEST mode so the full
    loop (classify -> decide -> draft) can be demonstrated and tested
    with zero AI calls and zero quota cost. The real version
    (action_agent.py) does this properly by actually reading the
    email; this is just a stand-in so TEST mode is fully complete too.
    """
    category = email_like.get("category")
    from_name = email_like.get("from_name", "there")
    subject = email_like.get("subject", "")

    if category == "subscription" and decision == "unsubscribe":
        text = (
            f"Hi {from_name} team,\n\n"
            f"Please cancel/unsubscribe me from this service.\n\n"
            f"Thank you."
        )
        summary = f"Unsubscribe request drafted for {from_name}"
    elif category == "needs_reply" and decision == "suggest_reply":
        text = (
            f"Hi {from_name},\n\n"
            f"Thanks for your message about \"{subject}\". I'll get back to you soon.\n\n"
            f"Best."
        )
        summary = f"Reply suggestion drafted for {from_name}"
    else:
        text = "No action needed."
        summary = "No action needed"

    return text, summary


def maybe_draft_action(email_like, decision, action_client):
    """
    Drafts the actual text for this decision (a cancellation email, a
    reply, a deal summary) and saves it to the drafts outbox.

    If real AI is available, it asks the action agent to write it
    properly. If not (TEST mode), it uses a simple template instead -
    this keeps the full loop testable with zero quota cost.
    """
    if decision in ("keep", "ignore", "already_replied"):
        return None

    if action_client is not None:
        draft_text, summary = action_agent.draft_action_with_ai(
            email_like, decision, client=action_client
        )
        time.sleep(7)  # stay under the free tier's requests-per-minute limit
    else:
        draft_text, summary = fake_draft_text(email_like, decision)

    draft_entry = {
        "email_id": email_like.get("id"),
        "category": email_like.get("category"),
        "decision": decision,
        "subject": email_like.get("subject"),
        "summary": summary,
        "draft_text": draft_text,
    }
    state_store.add_draft(draft_entry)
    return draft_entry


def classify_email(email, ai_client=None):
    """
    Decides the category for one email.

    If a Gemini API key is set up, this calls the real AI classifier
    (ai_classifier.py), which reads the actual subject and body text.

    If no key is set up, it falls back to the placeholder behavior:
    reading the "category" already written into our mock data, so you
    can still test the rest of the pipeline (memory, checkpoint, etc)
    without needing an API key yet.
    """
    if ai_client is not None:
        return ai_classifier.classify_email_with_ai(email, client=ai_client)
    return email["category"]


def get_new_emails(all_emails, checkpoints):
    """Returns only emails that arrived after each account's checkpoint."""
    new_emails = []
    for email in all_emails:
        account = email["account"]
        last_seen = checkpoints.get(account, MIN_TIMESTAMP)
        if email["timestamp"] > last_seen:
            new_emails.append(email)
    return new_emails


def update_checkpoints(checkpoints, processed_emails):
    """Moves each account's checkpoint forward to the latest email we saw."""
    for email in processed_emails:
        account = email["account"]
        if email["timestamp"] > checkpoints.get(account, MIN_TIMESTAMP):
            checkpoints[account] = email["timestamp"]
    return checkpoints


def run_cycle(data_folder):
    print("=" * 60)
    print(f"Running agent cycle at {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    ai_client = None
    action_client = None
    if ai_classifier.is_ai_available():
        print("\nMode: REAL AI classification (ADK agent + Gemini key found)")
        ai_client = ai_classifier.get_client()
        action_client = action_agent.get_client()
    else:
        print("\nMode: TEST mode (no Gemini key found - using mock answers)")

    all_emails = data_loader.load_all_emails(data_folder)
    checkpoints = state_store.load_checkpoints()
    decisions = state_store.load_decisions()
    pending = state_store.load_pending()
    pending_ids = {item["id"] for item in pending}

    # First, re-check the EXISTING waiting list against decisions.
    # If the user decided something since last run, remove it now -
    # don't wait for a new email to trigger the check.
    still_pending = []
    resolved_from_pending = []
    for item in pending:
        key = item["decision_key"]
        if key in decisions:
            resolved_from_pending.append((item, decisions[key]))
        else:
            still_pending.append(item)
    pending = still_pending
    pending_ids = {item["id"] for item in pending}

    if resolved_from_pending:
        print(f"\nCleared from waiting list (you already decided): {len(resolved_from_pending)}")
        for item, decision in resolved_from_pending:
            print(f"  - [{item['category']}] '{item['subject']}' -> decision: {decision}")
            draft = maybe_draft_action(item, decision, action_client)
            if draft:
                print(f"    Draft created: {draft['summary']}")

    new_emails = get_new_emails(all_emails, checkpoints)
    print(f"\nNew emails found: {len(new_emails)} (out of {len(all_emails)} total)")

    emails_to_process = new_emails
    if ai_client is not None and len(new_emails) > MAX_AI_EMAILS_PER_RUN:
        emails_to_process = new_emails[:MAX_AI_EMAILS_PER_RUN]
        remaining = len(new_emails) - len(emails_to_process)
        print(f"(Real AI mode: processing the first {len(emails_to_process)} now to respect "
              f"the daily quota - the other {remaining} will be picked up on a future run)")

    auto_resolved = []
    newly_pending = []

    for email in emails_to_process:
        category = classify_email(email, ai_client=ai_client)
        email["category"] = category

        if ai_client is not None:
            time.sleep(7)  # stay under the free tier's ~10 requests-per-minute limit

        if not email["requires_decision"]:
            continue  # noise, tickets, challenges etc. - just informational, no action needed

        key = email["decision_key"]
        if key in decisions:
            # We already know what the user wants for this vendor/sender
            auto_resolved.append((email, decisions[key]))
        elif email["id"] not in pending_ids:
            pending.append({
                "id": email["id"],
                "account": email["account"],
                "category": category,
                "subcategory": email.get("subcategory", ""),
                "decision_key": key,
                "subject": email["subject"],
                "from_name": email["from_name"],
                "from_email": email["from_email"],
                "body": email["body"],
                "timestamp": email.get("timestamp", ""),
            })
            newly_pending.append(email)

    # Report
    print(f"\nAuto-resolved using saved decisions: {len(auto_resolved)}")
    for email, decision in auto_resolved:
        print(f"  - [{email['category']}] '{email['subject']}' -> already decided: {decision}")
        draft = maybe_draft_action(email, decision, action_client)
        if draft:
            print(f"    Draft created: {draft['summary']}")

    print(f"\nNewly added to the waiting list: {len(newly_pending)}")
    for email in newly_pending:
        print(f"  - [{email['category']}] '{email['subject']}' from {email['from_name']}")

    print(f"\nStill waiting on your decision (total): {len(pending)}")
    for item in pending:
        print(f"  - [{item['category']}] '{item['subject']}' from {item['from_name']}")

    # Save state for next run
    checkpoints = update_checkpoints(checkpoints, emails_to_process)
    state_store.save_checkpoints(checkpoints)
    state_store.save_pending(pending)

    print("\nCheckpoint and pending list saved.\n")


if __name__ == "__main__":
    data_folder = os.path.join(os.path.dirname(__file__), "data")
    run_cycle(data_folder)
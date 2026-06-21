"""
decide.py

Goes through your waiting list ONE item at a time, shows you the full
email (not just the subject), and asks what you want to do about it.

Run it any time after pipeline.py with:
    python decide.py

For each item you can:
  - type a decision (e.g. "cancel", "keep", "reply", "ignore", "act")
  - press Enter alone to SKIP it (come back to it next time)
  - type "q" to stop entirely for now
"""

import state_store

DECISION_OPTIONS = {
    "subscription": ["cancel", "keep"],
    "deal": ["act", "ignore"],
    "needs_reply": ["reply", "ignore"],
}


def show_email(item, index, total):
    print("\n" + "=" * 60)
    print(f"Item {index} of {total}   [{item['category']}]")
    print("=" * 60)
    print(f"From:    {item.get('from_name', 'unknown')} <{item.get('from_email', '')}>")
    print(f"Account: {item.get('account', '')}")
    print(f"Subject: {item['subject']}")
    body = item.get("body", "")
    if body:
        print(f"\n{body}")


def main():
    pending = state_store.load_pending()

    if not pending:
        print("Nothing is waiting for a decision right now.")
        return

    print(f"You have {len(pending)} items waiting for a decision.")
    print("For each one: type your decision, press Enter to skip it, or type 'q' to stop.\n")

    decided_count = 0

    for i, item in enumerate(pending, start=1):
        show_email(item, i, len(pending))

        options = DECISION_OPTIONS.get(item["category"], ["keep", "ignore"])
        prompt = f"\nWhat do you want to do? ({' / '.join(options)}, Enter to skip, q to stop): "

        while True:
            answer = input(prompt).strip().lower()

            if answer == "q":
                print(f"\nStopped. You decided on {decided_count} item(s) this time.")
                print("Run pipeline.py to see these applied (drafts get created too, if AI is on).")
                return

            if answer == "":
                print("Skipped - it'll show up again next time.")
                break

            if answer in options:
                # Same key the agent uses internally (vendor+account for
                # subscriptions/deals, the message's own id for needs_reply) -
                # you never have to think about that part, it's handled here.
                state_store.save_decision(item["decision_key"], answer)
                print(f"Saved: {answer}")
                decided_count += 1
                break

            print(f"Please type one of: {', '.join(options)} (or Enter to skip, q to stop)")

    print(f"\nAll done! You decided on {decided_count} of {len(pending)} item(s).")
    print("Run pipeline.py to see these applied (drafts get created too, if AI is on).")


if __name__ == "__main__":
    main()
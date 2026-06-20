"""
decide.py

A simple way to make decisions on the items in your waiting list,
without needing to know how the agent stores things internally.

Run it any time after pipeline.py with:
    python decide.py

It shows you the list, you type a number, you pick what to do. That's it.
"""

import state_store

DECISION_OPTIONS = {
    "subscription": ["cancel", "keep"],
    "deal": ["act", "ignore"],
    "needs_reply": ["reply", "ignore"],
}


def main():
    pending = state_store.load_pending()

    if not pending:
        print("Nothing is waiting for a decision right now.")
        return

    print(f"You have {len(pending)} items waiting for a decision:\n")
    for i, item in enumerate(pending, start=1):
        print(f"{i}. [{item['category']}] '{item['subject']}' from {item['from_name']}")

    print("\nType a number to decide on it, or just press Enter to stop.")

    while True:
        choice = input("\nWhich number? ").strip()
        if not choice:
            break

        try:
            index = int(choice) - 1
            item = pending[index]
        except (ValueError, IndexError):
            print("That's not a valid number, try again.")
            continue

        options = DECISION_OPTIONS.get(item["category"], ["keep", "ignore"])
        decision = input(f"What do you want to do? ({' / '.join(options)}): ").strip().lower()

        if decision not in options:
            print(f"Please type one of: {', '.join(options)}")
            continue

        # This is the important part: we save the decision using the
        # SAME key the agent itself uses internally (vendor+account for
        # subscriptions/deals, the message's own id for needs_reply) -
        # you never have to think about that part, it's handled here.
        state_store.save_decision(item["decision_key"], decision)
        print(f"Saved: '{item['subject']}' -> {decision}")

    print("\nDone. Run pipeline.py again to see these applied (drafts get created too, if AI is on).")


if __name__ == "__main__":
    main()
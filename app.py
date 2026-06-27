"""
app.py

A simple web interface for the Inbox Intelligence Agent, built with
Streamlit. This does NOT replace any of the existing code - it just
puts a clickable screen on top of state_store.py, data_loader.py, and
pipeline.py, which all stay exactly as they are.

Run it with:
    streamlit run app.py

This opens a browser tab automatically.
"""

import os
from datetime import datetime, timezone

import streamlit as st

import data_loader
import state_store
import pipeline
import action_agent

DATA_FOLDER = os.path.join(os.path.dirname(__file__), "data")

DECISION_OPTIONS = {
    "subscription": ["unsubscribe", "keep", "ignore"],
    "deal": ["ignore"],
    "needs_reply": ["suggest_reply", "already_replied", "ignore"],
}

BUTTON_LABELS = {
    "unsubscribe": "Unsubscribe",
    "keep": "Keep – stay informed",
    "ignore": "Ignore at all",
    "already_replied": "Already replied",
    "suggest_reply": "Suggest me a reply",
}

st.set_page_config(page_title="Subscription Sweep", page_icon="📥", layout="wide")
st.title("📥 Subscription Sweep — Inbox Intelligence Agent")


# ---------- Sidebar: mode + run button + reset ----------

with st.sidebar:
    st.header("Controls")

    force_test = st.checkbox(
        "Force TEST mode (skip AI, no quota used)",
        value=os.environ.get("FORCE_TEST_MODE", "false").lower() == "true",
    )
    os.environ["FORCE_TEST_MODE"] = "true" if force_test else "false"

    if st.button("▶️ Run agent now", use_container_width=True):
        with st.spinner("Running the agent..."):
            log_lines = []
            # Capture pipeline.py's print() output so we can show it here too
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                pipeline.run_cycle(DATA_FOLDER)
            st.session_state["last_run_log"] = buf.getvalue()
        st.rerun()

    st.divider()

    confirm_reset = st.checkbox("I understand this wipes everything")
    if st.button("🗑️ Reset all memory", disabled=not confirm_reset, use_container_width=True):
        state_store.reset_state()
        st.session_state.pop("last_run_log", None)
        st.rerun()

    if "last_run_log" in st.session_state:
        with st.expander("Last run output"):
            st.text(st.session_state["last_run_log"])


# ---------- Quick stats ----------

if "skipped_ids" not in st.session_state:
    st.session_state["skipped_ids"] = set()

pending = state_store.load_pending()
drafts = state_store.load_drafts()
decisions = state_store.load_decisions()

col1, col2, col3 = st.columns(3)
col1.metric("Waiting for a decision", len(pending))
col2.metric("Drafts created", len(drafts))
col3.metric("Decisions remembered", len(decisions))


# ---------- Main tabs ----------

all_emails = data_loader.load_all_emails(DATA_FOLDER)
email_by_id = {e["id"]: e for e in all_emails}

tab1, tab2, tab3 = st.tabs(["📋 Waiting List", "✉️ Drafts", "🧠 Memory"])

visible_pending = [p for p in pending if p["id"] not in st.session_state["skipped_ids"]]

with tab1:
    if not visible_pending:
        st.info("Nothing is waiting for a decision right now. Click 'Run agent now' to check for new emails.")
    else:
        for item in visible_pending:
            header = f"[{item['category']}] {item['subject']} — from {item['from_name']}"
            sug_key = f"suggestion_{item['id']}"

            with st.expander(header):
                st.write(f"**Account:** {item['account']}")
                st.write(f"**From:** {item.get('from_name', '')} <{item.get('from_email', '')}>")

                if item["category"] == "deal":
                    original = email_by_id.get(item["id"], {})
                    ts = item.get("timestamp") or original.get("timestamp", "")
                    subcategory = item.get("subcategory") or original.get("subcategory", "")
                    body_lower = item.get("body", "").lower()

                    if ts:
                        try:
                            email_date = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            days_ago = (datetime.now(timezone.utc) - email_date).days
                            age_label = f"{days_ago} day{'s' if days_ago != 1 else ''} ago"
                        except ValueError:
                            age_label = ""
                    else:
                        age_label = ""

                    TIME_WORDS = ("expires", "expiring", "ends", "end of", "limited time",
                                  "this week", "this month", "deadline", "last day",
                                  "days left", "hours left", "valid until", "valid for")
                    is_time_sensitive = (
                        subcategory == "limited_time_offer"
                        or any(w in body_lower for w in TIME_WORDS)
                    )

                    if is_time_sensitive:
                        age_part = f" — received {age_label}" if age_label else ""
                        st.warning(f"⏰ Time-sensitive deal{age_part}. Check if it's still valid.")
                    elif age_label:
                        st.caption(f"Received {age_label}")

                st.write(item.get("body", ""))

                if sug_key in st.session_state:
                    sug = st.session_state[sug_key]
                    st.divider()
                    st.write("**Suggested reply:**")
                    st.code(sug["draft_text"], language=None)
                    sc1, sc2, sc3 = st.columns(3)
                    if sc1.button("Done — I replied", key=f"{item['id']}_done"):
                        state_store.save_decision(item["decision_key"], "suggest_reply")
                        remaining = [p for p in state_store.load_pending() if p["id"] != item["id"]]
                        state_store.save_pending(remaining)
                        state_store.add_draft({
                            "email_id": item["id"],
                            "category": item["category"],
                            "decision": "suggest_reply",
                            "subject": item["subject"],
                            "summary": sug.get("summary", ""),
                            "draft_text": sug["draft_text"],
                        })
                        del st.session_state[sug_key]
                        st.rerun()
                    if sc2.button("Skip for now", key=f"{item['id']}_skip_sug"):
                        del st.session_state[sug_key]
                        st.rerun()
                    if sc3.button("Ignore at all", key=f"{item['id']}_ignore_sug"):
                        state_store.save_decision(item["decision_key"], "ignore")
                        remaining = [p for p in state_store.load_pending() if p["id"] != item["id"]]
                        state_store.save_pending(remaining)
                        del st.session_state[sug_key]
                        st.rerun()
                else:
                    options = DECISION_OPTIONS.get(item["category"], ["keep", "ignore"])
                    cols = st.columns(len(options) + 1)

                    for i, opt in enumerate(options):
                        label = BUTTON_LABELS.get(opt, opt.replace("_", " ").capitalize())
                        if cols[i].button(label, key=f"{item['id']}_{opt}"):
                            if opt == "suggest_reply":
                                with st.spinner("Reading the message and preparing a suggestion..."):
                                    try:
                                        use_ai = action_agent.is_ai_available() and not force_test
                                        if use_ai:
                                            client = action_agent.get_client()
                                            draft_text, summary = action_agent.draft_action_with_ai(
                                                item, opt, client=client
                                            )
                                        else:
                                            draft_text, summary = pipeline.fake_draft_text(item, opt)
                                    except Exception as e:
                                        draft_text = f"Could not generate suggestion: {e}"
                                        summary = "generation failed"
                                st.session_state[sug_key] = {
                                    "draft_text": draft_text,
                                    "summary": summary,
                                }
                                st.rerun()
                            else:
                                state_store.save_decision(item["decision_key"], opt)
                                remaining = [p for p in state_store.load_pending() if p["id"] != item["id"]]
                                state_store.save_pending(remaining)
                                st.rerun()

                    if cols[-1].button("Skip for now", key=f"{item['id']}_skip"):
                        st.session_state["skipped_ids"].add(item["id"])
                        st.rerun()

with tab2:
    if not drafts:
        st.info("No drafts yet. Make a decision in the Waiting List tab, then click 'Run agent now'.")
    else:
        for d in reversed(drafts):
            header = f"[{d['category']}] {d['subject']} — {d['decision']}"
            with st.expander(header):
                st.caption(d.get("summary", ""))
                st.code(d.get("draft_text", ""), language=None)

with tab3:
    if not decisions:
        st.info("No decisions saved yet.")
    else:
        by_key = {}
        for email in all_emails:
            by_key.setdefault(email["decision_key"], []).append(email)

        for key, decision in decisions.items():
            matches = by_key.get(key, [])
            if matches:
                example = matches[0]
                label = f"**[{example['category']}]** {example['subject']} — {example['from_name']} ({example['account']})"
            else:
                label = f"`{key}`"
            col_text, col_btn = st.columns([6, 1])
            col_text.write(f"{label} → **{decision}**")
            if col_btn.button("↩ Reset", key=f"reset_{key}"):
                state_store.delete_decision(key)
                st.rerun()

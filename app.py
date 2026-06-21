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

import streamlit as st

import data_loader
import state_store
import pipeline

DATA_FOLDER = os.path.join(os.path.dirname(__file__), "data")

DECISION_OPTIONS = {
    "subscription": ["cancel", "keep"],
    "deal": ["act", "ignore"],
    "needs_reply": ["reply", "ignore"],
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

pending = state_store.load_pending()
drafts = state_store.load_drafts()
decisions = state_store.load_decisions()

col1, col2, col3 = st.columns(3)
col1.metric("Waiting for a decision", len(pending))
col2.metric("Drafts created", len(drafts))
col3.metric("Decisions remembered", len(decisions))


# ---------- Main tabs ----------

tab1, tab2, tab3 = st.tabs(["📋 Waiting List", "✉️ Drafts", "🧠 Memory"])

with tab1:
    if not pending:
        st.info("Nothing is waiting for a decision right now. Click 'Run agent now' to check for new emails.")
    else:
        for item in pending:
            header = f"[{item['category']}] {item['subject']} — from {item['from_name']}"
            with st.expander(header):
                st.write(f"**Account:** {item['account']}")
                st.write(f"**From:** {item.get('from_name', '')} <{item.get('from_email', '')}>")
                st.write(item.get("body", ""))

                options = DECISION_OPTIONS.get(item["category"], ["keep", "ignore"])
                cols = st.columns(len(options) + 1)

                for i, opt in enumerate(options):
                    if cols[i].button(opt.capitalize(), key=f"{item['id']}_{opt}"):
                        state_store.save_decision(item["decision_key"], opt)
                        # Remove it from the visible waiting list right away.
                        # The actual draft gets written next time "Run agent
                        # now" is clicked - that keeps AI calls batched and
                        # rate-limited, instead of firing one per click.
                        remaining = [p for p in state_store.load_pending() if p["id"] != item["id"]]
                        state_store.save_pending(remaining)
                        st.success(f"Saved: {opt}")
                        st.rerun()

                if cols[-1].button("Skip for now", key=f"{item['id']}_skip"):
                    st.info("Left as-is - it'll still be here next time.")

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
        all_emails = data_loader.load_all_emails(DATA_FOLDER)
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
            st.write(f"{label} → **{decision}**")

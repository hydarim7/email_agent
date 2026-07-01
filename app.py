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
import io
import data_loader
import state_store
import pipeline
import re
import action_agent  
import contextlib
DATA_FOLDER = os.path.join(os.path.dirname(__file__), "data")

DECISION_OPTIONS = {
    "subscription": ["cancel", "keep"],
    "deal": ["act", "ignore"],
    "needs_reply": ["reply", "ignore"],
}
CATEGORY_CONFIG = {
    "needs_reply":  {"label": "💬 Needs Reply",   "color": "#1a73e8", "bg": "#e8f0fe"},
    "subscription": {"label": "💳 Subscription",  "color": "#e65c00", "bg": "#fce8d8"},
    "deal":         {"label": "🤑 Deal",           "color": "#1e7e34", "bg": "#d4edda"},
}



def extract_billing_date(body: str):
    """Pull the first date-like string from an email body. Returns a date or None."""
    patterns = [
        r"(\w+ \d{1,2},?\s*\d{4})",          # February 10, 2026
        r"(\d{1,2}/\d{1,2}/\d{4})",           # 02/10/2026
        r"(\d{4}-\d{2}-\d{2})",               # 2026-02-10
    ]
    fmts = [
        ["%B %d %Y", "%B %d, %Y", "%b %d %Y", "%b %d, %Y"],
        ["%m/%d/%Y"],
        ["%Y-%m-%d"],
    ]
    for pattern, date_fmts in zip(patterns, fmts):
        for m in re.finditer(pattern, body):
            raw = m.group(1).replace(",", "").strip()
            for fmt in date_fmts:
                try:
                    return datetime.strptime(raw, fmt).date()
                except ValueError:
                    continue
    return None

def badge(category: str) -> str:
    cfg = CATEGORY_CONFIG.get(category, {"label": category, "color": "#555", "bg": "#eee"})
    return (
        f"<span style='background:{cfg['bg']}; color:{cfg['color']}; "
        f"font-size:11px; font-weight:600; padding:2px 8px; "
        f"border-radius:12px; margin-right:6px;'>{cfg['label']}</span>"
    )

def extract_amount(body: str):
    """Pull the first dollar/euro amount from the body."""
    m = re.search(r"[\$€£][\d,]+\.?\d*", body)
    return m.group(0) if m else None


def render_decision_buttons(item):
    options = DECISION_OPTIONS.get(item["category"], ["keep", "ignore"])
    cols = st.columns(len(options) + 1)
    for i, opt in enumerate(options):
        btn_color = {
            "cancel": "🔴", "keep": "🟢",
            "reply": "🔵", "ignore": "⚪",
            "act": "🟠",
        }.get(opt, "")
        if cols[i].button(f"{btn_color} {opt.capitalize()}", key=f"{item['id']}_{opt}"):
            # ✅ CHANGE: if reply, generate draft inline instead of saving+rerunning
            if opt == "reply":
                with st.spinner("Generating reply..."):
                    draft, summary = action_agent.draft_action_with_ai(item, "reply")
                st.session_state[f"draft_{item['id']}"] = draft
            else:
                state_store.save_decision(item["decision_key"], opt)
                remaining = [p for p in state_store.load_pending() if p["id"] != item["id"]]
                state_store.save_pending(remaining)
                st.toast(f"✅ Saved: {opt} for {item['from_name']}", icon="✅")
                st.rerun()
    if cols[-1].button("⏭️ Skip", key=f"{item['id']}_skip"):
        st.toast("Skipped — still here next time", icon="⏭️")

    # ✅ ADD THIS BLOCK: show editable draft + send button if reply was clicked
    draft_key = f"draft_{item['id']}"
    if draft_key in st.session_state:
        st.markdown("**✏️ Edit your reply before sending:**")
        edited = st.text_area("Reply", value=st.session_state[draft_key], height=150, key=f"edit_{item['id']}")
        col_send, col_discard = st.columns([1, 4])
        if col_send.button("📤 Send", key=f"send_{item['id']}"):
            state_store.save_decision(item["decision_key"], "reply")
            remaining = [p for p in state_store.load_pending() if p["id"] != item["id"]]
            state_store.save_pending(remaining)
            # save the edited draft
            state_store.add_draft({
                "id": item["id"],
                "subject": item["subject"],
                "category": item["category"],
                "decision": "reply",
                "draft_text": edited,
                "summary": f"Reply to {item['from_name']}",
                })
            del st.session_state[draft_key]
            st.toast("✅ Reply saved to Drafts!", icon="✅")
            st.rerun()
        if col_discard.button("🗑️ Discard", key=f"discard_{item['id']}"):
            del st.session_state[draft_key]
            st.rerun()


def render_email_card(item):
    body = item.get("body", "")
    amount = extract_amount(body)

    amount_tag = (
        f"<span style='background:#fff3cd; color:#856404; font-size:11px; "
        f"font-weight:600; padding:2px 8px; border-radius:12px; margin-right:6px;'>"
        f"💰 {amount}</span>"
    ) if amount else ""

   

    with st.expander(item["subject"]):
        col_info, col_body = st.columns([1, 2])
        with col_info:
            st.markdown(f"**From:** {item.get('from_name')} ")
            st.markdown(f"**Email:** `{item.get('from_email', '')}`")
            st.markdown(f"**Account:** `{item['account']}`")
        with col_body:
            thread = item.get("thread_history", [])
            if thread:
                show_key = f"show_thread_{item['id']}"
                if show_key not in st.session_state:
                    st.session_state[show_key] = False
                if st.button(
                    f"{'🔼 Hide' if st.session_state[show_key] else '🔽 Show'} conversation history ({len(thread)} messages)",
                    key=f"btn_{show_key}"
                ):
                    st.session_state[show_key] = not st.session_state[show_key]
                if st.session_state[show_key]:
                    for msg in thread:
                        st.markdown(
                            f"<div style='border-left:3px solid #ccc; padding-left:10px;"
                            f"color:#555; margin-bottom:8px; font-size:13px;'>"
                            f"<strong>{msg['from_name']}</strong><br>{msg['body']}</div>",
                            unsafe_allow_html=True,
                        )
                    st.markdown("**📩 Latest message:**")
            st.markdown(f"> {body}")
        st.divider()
        render_decision_buttons(item)

st.set_page_config(page_title="Subscription Sweep", page_icon="📥", layout="wide")
st.title("📥 Subscription Sweep — Inbox Intelligence Agent")

# ---------- Sidebar: mode + run button + reset ----------

with st.sidebar:
    st.header("⚙️ Controls")

    force_test = st.checkbox(
        "Force TEST mode (no AI quota used)",
        value=os.environ.get("FORCE_TEST_MODE", "false").lower() == "true",
    )
    os.environ["FORCE_TEST_MODE"] = "true" if force_test else "false"

    if st.button("▶️ Run agent now", use_container_width=True, type="primary"):
        with st.spinner("Running the agent..."):
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
        with st.expander("Last run log"):
            st.text(st.session_state["last_run_log"])

# ---------- Quick stats ----------

pending = state_store.load_pending()
drafts = state_store.load_drafts()
decisions = state_store.load_decisions()

c1, c2, c3, c4 = st.columns(4)
c1.metric("⏳ Waiting", len(pending))
c2.metric("✉️ Drafts",  len(drafts))
c3.metric("🧠 Remembered", len(decisions))
subs_pending = [p for p in pending if p["category"] == "subscription"]
c4.metric("💳 Subscriptions", len(subs_pending))

st.divider()

# ── account filter ────────────────────────────────────────────────────────────

accounts = sorted({p["account"] for p in pending})
filter_options = ["All"] + accounts
selected_account = st.radio(
    "Filter by account:",
    filter_options,
    horizontal=True,
    label_visibility="collapsed",
)

filtered = pending if selected_account == "All" else [
    p for p in pending if p["account"] == selected_account
]


# ---------- Main tabs ----------

tab1, tab2, tab3 = st.tabs(["📋 Waiting List", "✉️ Drafts", "🧠 Memory"])

with tab1:
    if not pending:
        st.info("Nothing is waiting for a decision right now. Click 'Run agent now' to check for new emails.")
    else:
        # Group by category
        for category, cfg in CATEGORY_CONFIG.items():
            group = [p for p in filtered if p["category"] == category]
            if not group:
                continue

            st.markdown(
                f"<h3 style='color:{cfg['color']}; margin-top:1.5rem;'>"
                f"{cfg['label']} <span style='font-size:16px; color:#888;'>({len(group)})</span>"
                f"</h3>",
                unsafe_allow_html=True,
            )

            for item in group:
                render_email_card(item)

with tab2:
    if not drafts:
        st.info("No drafts yet. Make a decision in the Waiting List tab, then click 'Run agent now'.")
    else:
        for d in reversed(drafts):
            cfg = CATEGORY_CONFIG.get(d["category"], {"label": d["category"], "color": "#555", "bg": "#eee"})
            with st.expander(f"{d['subject']} — {d['decision'].upper()}"):
                st.markdown(
                    f"{badge(d['category'])}"
                    f"<span style='font-size:12px; color:#888;'>{d.get('summary','')}</span>",
                    unsafe_allow_html=True,
                )
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
            decision_color = {
                "cancel": "#dc3545", "keep": "#28a745",
                "reply": "#1a73e8",  "ignore": "#888",
                "act": "#e65c00",
            }.get(decision, "#555")

            if matches:
                ex = matches[0]
                st.markdown(
                    f"{badge(ex['category'])} **{ex['subject']}** — {ex['from_name']} "
                    f"<span style='color:{decision_color}; font-weight:700;'>→ {decision.upper()}</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"`{key}` <span style='color:{decision_color}; font-weight:700;'>→ {decision.upper()}</span>",
                    unsafe_allow_html=True,
                )
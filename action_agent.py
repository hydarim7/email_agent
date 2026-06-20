"""
action_agent.py

This is the SECOND ADK agent. The classifier agent (ai_classifier.py)
decides what KIND of email something is. This agent takes that result
plus the decision you made (cancel / act / reply / keep / ignore) and
writes the actual draft text - a cancellation email, or a suggested
reply.

Having two separate agents working together (classifier + action) is
what makes this a real multi-agent system, not just one big function -
this directly satisfies the "Agent / Multi-agent system (ADK)" item
in the hackathon's evaluation criteria.

Setup: same as ai_classifier.py - this needs GOOGLE_API_KEY set and
"pip install google-adk pydantic" already done.
"""

import os
import json
import asyncio


def _build_agent():
    from pydantic import BaseModel, Field
    from google.adk.agents import Agent

    class DraftedAction(BaseModel):
        draft_text: str = Field(description="The actual email or message text to send")
        action_summary: str = Field(description="One short sentence describing what this draft does")

    return Agent(
        name="action_agent",
        model="gemini-2.5-flash-lite",
        instruction="""You are an assistant that writes short, polite,
ready-to-send drafts based on a decision the user already made.

You will be given:
- the category of the email (subscription, deal, or needs_reply)
- the decision the user made (cancel, keep, act, ignore, reply)
- the original email's subject, sender, and body

Rules:
- If category is "subscription" and decision is "cancel": write a
  short, polite cancellation request addressed to the company, asking
  them to cancel the subscription/service. Keep it under 80 words.
- If category is "deal" and decision is "act": write a short note to
  the USER (not the company) summarizing why this deal is worth taking
  and what to do next. Keep it under 40 words.
- If category is "needs_reply" and decision is "reply": write a short,
  natural reply to the sender, matching the relationship implied by
  the email (casual for friends/family, professional for colleagues
  or professors). Keep it under 60 words.
- For any other combination (decision is "keep" or "ignore"): the
  draft_text should just say "No action needed."

Never invent account numbers, payment details, or personal information
that wasn't in the original email. Always answer using the required
JSON structure.""",
        output_schema=DraftedAction,
    )


async def _draft_async(email, decision, runner):
    from google.genai import types

    session = await runner.session_service.create_session(
        app_name="inbox_intelligence", user_id="local_user"
    )
    prompt = (
        f"Category: {email.get('category')}\n"
        f"Decision: {decision}\n"
        f"From: {email.get('from_name')} <{email.get('from_email')}>\n"
        f"Subject: {email.get('subject')}\n"
        f"Body:\n{email.get('body')}"
    )

    final_text = None
    async for event in runner.run_async(
        user_id="local_user",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text

    return final_text


def get_client():
    """Creates one ADK Runner wrapping the action agent, reused across calls."""
    from google.adk.runners import InMemoryRunner
    agent = _build_agent()
    return InMemoryRunner(agent=agent, app_name="inbox_intelligence")


def draft_action_with_ai(email, decision, client=None):
    """
    Returns (draft_text, action_summary) for one email + decision pair.
    Retries once automatically if the model is temporarily busy.
    """
    if client is None:
        client = get_client()

    last_error = None
    for attempt in range(2):
        try:
            final_text = asyncio.run(_draft_async(email, decision, client))
            if final_text is None:
                last_error = "no response from action agent"
                continue
            result = json.loads(final_text)
            return result.get("draft_text", "No action needed."), result.get("action_summary", "")
        except Exception as e:
            last_error = e
            is_temporary = "503" in str(e) or "UNAVAILABLE" in str(e)
            if is_temporary and attempt == 0:
                print("  (model temporarily busy, retrying in 5 seconds...)")
                import time
                time.sleep(5)
                continue
            break

    print(f"  (action agent failed: {last_error}, no draft generated)")
    return "No action needed.", "draft failed"


def is_ai_available():
    if not os.environ.get("GOOGLE_API_KEY"):
        return False
    try:
        import google.adk  # noqa: F401
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    # Quick manual test - run this file directly to check it works:
    #     python action_agent.py
    if not is_ai_available():
        print("ADK not available - set GOOGLE_API_KEY first.")
    else:
        test_email = {
            "category": "subscription",
            "from_name": "Netflix",
            "from_email": "info@account.netflix.com",
            "subject": "Your Netflix payment receipt",
            "body": "This confirms your monthly payment of EUR 17.99 was processed.",
        }
        draft, summary = draft_action_with_ai(test_email, decision="cancel")
        print(f"Summary: {summary}")
        print(f"Draft:\n{draft}")

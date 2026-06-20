"""
ai_classifier.py

REAL classifier - built using Google's ADK (Agent Development Kit).

The hackathon rules specifically ask for "Agent / Multi-agent system
(ADK)" to be visible in your code, so this version defines a real
ADK Agent and runs it through ADK's Runner, instead of calling
Gemini directly like the earlier version did.

----------------------------------------------------------------
SETUP NEEDED BEFORE THIS WORKS (do this on your own computer):
----------------------------------------------------------------
1. Install ADK:
       pip install google-adk pydantic

2. Get a free API key from Google AI Studio:
       https://aistudio.google.com/apikey

3. Save the key as an environment variable (ADK looks for this exact name):

   Windows (PowerShell):
       $env:GOOGLE_API_KEY="paste-your-key-here"

   Mac/Linux:
       export GOOGLE_API_KEY="paste-your-key-here"

Note: this is a different variable name (GOOGLE_API_KEY) than the
earlier non-ADK version used (GEMINI_API_KEY). If you set the old one
before, set this one too.

Once the key is set, pipeline.py will automatically switch to
"REAL AI classification" by itself - no other code changes needed.
"""

import os
import json
import asyncio


def _load_dotenv_if_present():
    """
    Reads a .env file in the same folder (if one exists) and loads any
    keys from it into the environment, so GOOGLE_API_KEY=... in a .env
    file works the same as typing it into the terminal.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # python-dotenv not installed - .env file just won't be read, that's OK


_load_dotenv_if_present()

ALLOWED_CATEGORIES = [
    "subscription",
    "deal",
    "needs_reply",
    "noise",
    "job_application",
    "ticket_purchase",
    "challenge",
]

INSTRUCTION = f"""You are an email classification assistant.

Read the email below and choose exactly ONE category from this list:
{', '.join(ALLOWED_CATEGORIES)}

- subscription: a recurring paid service, billing receipt, renewal notice, or price change
- deal: a discount, coupon, sale, or promotion - something with real value worth considering
- needs_reply: a message from a real person (friend, colleague, professor, recruiter) that expects a response
- ticket_purchase: a confirmation for an event, flight, train, or other ticket already bought
- job_application: anything related to a job you applied for (confirmation, interview, offer, rejection)
- challenge: an invitation to a contest, hackathon, or similar challenge
- noise: anything else - newsletters, generic marketing, app notifications, low-value content

Always answer using the required JSON structure."""


def _build_agent():
    """
    This is the actual ADK Agent definition - the part the hackathon
    rules want to see. It's a single agent right now (the classifier).
    The next agent we build (the action agent that drafts replies and
    cancellations) will be a second ADK agent, making this a real
    multi-agent system.

    Imports are kept INSIDE this function on purpose: this means
    ai_classifier.py can still be safely imported even before you've
    run "pip install google-adk pydantic" - pipeline.py will just
    fall back to TEST mode instead of crashing on startup.
    """
    from pydantic import BaseModel, Field
    from google.adk.agents import Agent

    class EmailClassification(BaseModel):
        """The shape of the answer we want back from the agent."""
        category: str = Field(description=f"Exactly one of: {', '.join(ALLOWED_CATEGORIES)}")
        reason: str = Field(description="One short sentence explaining why")

    return Agent(
        name="email_classifier",
        model="gemini-2.5-flash-lite",
        instruction=INSTRUCTION,
        output_schema=EmailClassification,
    )


def get_client():
    """
    Creates one ADK Runner wrapping our classifier agent. This gets
    reused across every email (faster than rebuilding it each time).
    In ADK terms this is a "Runner", but we keep the name get_client()
    so pipeline.py doesn't need to change.
    """
    from google.adk.runners import InMemoryRunner
    agent = _build_agent()
    return InMemoryRunner(agent=agent, app_name="inbox_intelligence")


async def _classify_async(email, runner):
    from google.genai import types

    session = await runner.session_service.create_session(
        app_name="inbox_intelligence", user_id="local_user"
    )
    prompt = (
        f"From: {email.get('from_name', 'unknown')} <{email.get('from_email', 'unknown')}>\n"
        f"Subject: {email.get('subject', '')}\n"
        f"Body:\n{email.get('body', '')}"
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


def classify_email_with_ai(email, client=None):
    """
    Sends one email through the ADK agent and returns one of
    ALLOWED_CATEGORIES. Falls back to "noise" if anything goes wrong
    (bad response, network issue, etc) so the pipeline never crashes
    because of one bad email.

    "client" here is actually the ADK Runner created by get_client().

    If the model is temporarily busy (a 503 error), this automatically
    waits a moment and tries one more time before giving up - this is
    a temporary glitch on Google's side, not a real classification
    failure, so it deserves a second chance.
    """
    if client is None:
        client = get_client()

    last_error = None
    for attempt in range(2):  # try once, then retry once more if needed
        try:
            final_text = asyncio.run(_classify_async(email, client))
            if final_text is None:
                last_error = "no response from ADK agent"
                continue

            result = json.loads(final_text)
            category = result.get("category", "noise")
            if category not in ALLOWED_CATEGORIES:
                print(f"  (unexpected AI answer '{category}', falling back to 'noise')")
                return "noise"
            return category

        except Exception as e:
            last_error = e
            is_temporary = "503" in str(e) or "UNAVAILABLE" in str(e)
            if is_temporary and attempt == 0:
                print("  (model temporarily busy, retrying in 5 seconds...)")
                import time
                time.sleep(5)
                continue
            break

    print(f"  (ADK agent call failed: {last_error}, falling back to 'noise')")
    return "noise"


def is_ai_available():
    """Checks if we have what we need to actually run the ADK agent."""
    if not os.environ.get("GOOGLE_API_KEY"):
        return False
    try:
        import google.adk  # noqa: F401
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    # Quick manual test - run this file directly to check your setup works:
    #     python ai_classifier.py
    test_email = {
        "from_name": "Netflix",
        "from_email": "info@account.netflix.com",
        "subject": "Your Netflix payment was successful",
        "body": "Hi, this confirms your monthly payment of EUR 17.99 was processed.",
    }

    if is_ai_available():
        runner = get_client()
        result = classify_email_with_ai(test_email, client=runner)
        print(f"ADK agent classified this email as: {result}")
    else:
        print("ADK not available - set GOOGLE_API_KEY and run: pip install google-adk pydantic")

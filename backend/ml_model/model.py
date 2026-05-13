# model_py/model.py

OLLAMA_MODEL = "llama3"

SYSTEM_PROMPT = """You are an email classification assistant.
Classify emails into EXACTLY ONE of these tags:

- urgent    : needs immediate action, deadline today, critical issue, emergency
- action    : requires a response or task, not time-critical
- fyi       : informational only, no reply needed
- spam      : promotional, unsolicited, or irrelevant

Rules:
1. Respond with valid JSON only — no explanation outside the JSON
2. Never use a tag not in the list above
3. If unsure between urgent and action, pick action
4. If unsure between fyi and spam, pick fyi
"""

FEW_SHOT_EXAMPLES = [
    {
        "subject": "Server down in production",
        "body": "Our main API has been returning 500s for the last 10 mins. Customers affected.",
        "tag": "urgent",
        "reason": "Production system failure actively affecting customers"
    },
    {
        "subject": "Please review my pull request",
        "body": "Hey, could you review PR #42 when you get a chance? No rush.",
        "tag": "action",
        "reason": "Requires a review response but not time-critical"
    },
    {
        "subject": "Notes from today's standup",
        "body": "Attaching the notes from today's meeting. No action needed from your side.",
        "tag": "fyi",
        "reason": "Informational only, no response required"
    },
    {
        "subject": "WIN A FREE IPHONE - CLICK NOW!!!",
        "body": "Congratulations! You have been selected. Click the link to claim your prize.",
        "tag": "spam",
        "reason": "Unsolicited promotional scam content"
    },
]

VALID_TAGS = {"urgent", "action", "fyi", "spam"}

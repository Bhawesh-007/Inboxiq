# model_py/predict.py
import ollama
import json
import sys
import os

# make sure model.py and train.py are importable
sys.path.insert(0, os.path.dirname(__file__))

from model import OLLAMA_MODEL, SYSTEM_PROMPT, VALID_TAGS
from train import build_few_shot_block


# ── Core classifier ──────────────────────────────────────────

def classify_email(subject: str, body: str = "") -> dict:
    """
    Classifies a single email using llama3 via Ollama.

    Returns:
        {
            "tag":    "urgent" | "action" | "fyi" | "spam",
            "reason": "one sentence explanation"
        }
    """
    few_shot = build_few_shot_block(max_examples=4)

    user_prompt = f"""{few_shot}

Now classify this new email:

Subject : {subject}
Body    : {body.strip() if body else "(no body provided)"}

Respond with ONLY this JSON — nothing else:
{{"tag": "<urgent|action|fyi|spam>", "reason": "<one sentence why>"}}"""

    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            format="json",            # forces model to output JSON
            options={
                "temperature": 0,     # deterministic — same input = same output
                "num_predict": 100,   # max tokens — keeps response short
            }
        )

        raw = response["message"]["content"].strip()
        result = json.loads(raw)

        # Sanitize — make sure tag is valid
        if result.get("tag") not in VALID_TAGS:
            return {
                "tag":    "fyi",
                "reason": f"Model returned unknown tag '{result.get('tag')}', defaulted to fyi"
            }

        return {
            "tag":    result["tag"],
            "reason": result.get("reason", "")
        }

    except json.JSONDecodeError as e:
        return {"tag": "fyi", "reason": f"JSON parse error: {str(e)}"}

    except ollama.ResponseError as e:
        return {"tag": "fyi", "reason": f"Ollama error: {str(e)}"}

    except Exception as e:
        return {"tag": "fyi", "reason": f"Unexpected error: {str(e)}"}


# ── Batch classifier ─────────────────────────────────────────

def classify_batch(emails: list) -> list:
    """
    Classify a list of emails.

    Input : [{"subject": "...", "body": "..."}, ...]
    Output: same list with "tag" and "reason" added to each item
    """
    results = []
    for i, email in enumerate(emails):
        print(f"  Classifying {i+1}/{len(emails)}: {email.get('subject','')[:50]}...")
        tag_data = classify_email(
            subject=email.get("subject", ""),
            body=email.get("body", "")
        )
        results.append({**email, **tag_data})
    return results


# ── Tag colors for terminal output ───────────────────────────

TAG_COLORS = {
    "urgent": "\033[91m",   # red
    "action": "\033[93m",   # yellow
    "fyi":    "\033[94m",   # blue
    "spam":   "\033[90m",   # grey
}
RESET = "\033[0m"
BOLD  = "\033[1m"

def colored_tag(tag: str) -> str:
    color = TAG_COLORS.get(tag, "")
    return f"{BOLD}{color}[{tag.upper():8}]{RESET}"


# ── Run directly to test ─────────────────────────────────────

if __name__ == "__main__":
    test_emails = [
        {
            "subject": "DB is down, users cannot login!",
            "body":    "Production database crashed 5 minutes ago. All users are getting 500 errors."
        },
        {
            "subject": "Can you review the proposal doc?",
            "body":    "Hey, when you get a chance could you look over the attached proposal and give feedback?"
        },
        {
            "subject": "Team outing photos from Friday",
            "body":    "Sharing the photos from last Friday's team outing. Hope you enjoy!"
        },
        {
            "subject": "Exclusive deal — 80% OFF today only!!!",
            "body":    "Don't miss this limited time offer. Click now to claim your discount coupon."
        },
        {
            "subject": "Deployment to prod needs your approval",
            "body":    "The release is ready. We need your sign-off before we push to production."
        },
        {
            "subject": "Updated leave policy — please read",
            "body":    "HR has updated the leave policy effective next month. No action needed, just read."
        },
    ]

    print(f"\n{'═'*60}")
    print(f"  StudentTrack — Email Classifier  (model: {OLLAMA_MODEL})")
    print(f"{'═'*60}\n")

    for email in test_emails:
        result = classify_email(email["subject"], email["body"])
        tag    = result["tag"]
        reason = result["reason"]
        print(f"{colored_tag(tag)} {email['subject']}")
        print(f"           {reason}\n")

    print(f"{'═'*60}\n")

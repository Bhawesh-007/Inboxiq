# model_py/train.py
import json
import os

EXAMPLES_FILE = os.path.join(os.path.dirname(__file__), "examples.json")


# ── Load / Save ──────────────────────────────────────────────

def load_examples() -> list:
    if not os.path.exists(EXAMPLES_FILE):
        return []
    with open(EXAMPLES_FILE, "r") as f:
        return json.load(f)


def save_examples(examples: list):
    with open(EXAMPLES_FILE, "w") as f:
        json.dump(examples, f, indent=2)


# ── Add a new labeled example ────────────────────────────────

def add_example(subject: str, body: str, correct_tag: str, reason: str = ""):
    """
    Call this whenever you want to teach the model a new case.
    The more examples you add, the better the classification gets.
    """
    valid = {"urgent", "action", "fyi", "spam"}
    if correct_tag not in valid:
        print(f"❌ Invalid tag '{correct_tag}'. Must be one of: {valid}")
        return

    examples = load_examples()
    examples.append({
        "subject": subject,
        "body":    body,
        "tag":     correct_tag,
        "reason":  reason
    })
    save_examples(examples)
    print(f"✅ Example added. Total examples: {len(examples)}")


# ── Build few-shot block to inject into prompt ───────────────

def build_few_shot_block(max_examples: int = 6) -> str:
    """
    Returns a formatted string of the most recent N examples.
    This is injected into the classify prompt to improve accuracy.
    """
    # Start with hardcoded base examples from model.py
    from model import FEW_SHOT_EXAMPLES
    base = FEW_SHOT_EXAMPLES.copy()

    # Add any user-trained examples on top
    trained = load_examples()
    all_examples = base + trained

    # Take the last max_examples
    recent = all_examples[-max_examples:]

    if not recent:
        return ""

    lines = ["Here are labeled examples to guide your classification:\n"]
    for ex in recent:
        lines.append(f'Subject : "{ex["subject"]}"')
        if ex.get("body"):
            snippet = ex["body"][:100] + ("..." if len(ex["body"]) > 100 else "")
            lines.append(f'Body    : "{snippet}"')
        lines.append(f'Answer  : {{"tag": "{ex["tag"]}", "reason": "{ex["reason"]}"}}\n')

    return "\n".join(lines)


# ── View all saved examples ──────────────────────────────────

def list_examples():
    examples = load_examples()
    if not examples:
        print("No custom examples saved yet.")
        return
    print(f"\n{'─'*60}")
    print(f"  {len(examples)} custom example(s) in examples.json")
    print(f"{'─'*60}")
    for i, ex in enumerate(examples, 1):
        print(f"\n[{i}] Tag    : {ex['tag'].upper()}")
        print(f"    Subject: {ex['subject']}")
        print(f"    Reason : {ex.get('reason', '—')}")
    print(f"\n{'─'*60}\n")


# ── Remove an example by index ───────────────────────────────

def remove_example(index: int):
    """index is 1-based (as shown in list_examples)"""
    examples = load_examples()
    if index < 1 or index > len(examples):
        print(f"❌ Index {index} out of range. You have {len(examples)} examples.")
        return
    removed = examples.pop(index - 1)
    save_examples(examples)
    print(f"✅ Removed: [{removed['tag']}] {removed['subject']}")


# ── Run directly to seed starter examples ───────────────────

if __name__ == "__main__":
    print("Seeding starter examples...\n")

    add_example(
        subject="URGENT: Payment failed — update billing now",
        body="Your subscription payment has failed. Please update your billing details within 24 hours or your account will be suspended.",
        correct_tag="urgent",
        reason="Time-sensitive account action required within 24 hours"
    )
    add_example(
        subject="Can you send me the report by EOD?",
        body="Hi, could you please share the Q3 report before end of day today? Need it for the client call.",
        correct_tag="action",
        reason="Requires sending a document, has a soft deadline"
    )
    add_example(
        subject="Office will be closed on Friday",
        body="Just a reminder that the office will remain closed this Friday for the public holiday.",
        correct_tag="fyi",
        reason="Informational announcement, no action needed"
    )
    add_example(
        subject="You have been pre-approved for a loan!",
        body="Dear customer, you have been pre-approved for a personal loan of up to Rs. 5,00,000. Apply now!",
        correct_tag="spam",
        reason="Unsolicited financial promotional offer"
    )
    add_example(
        subject="Production DB CPU at 98% — check immediately",
        body="Alert: Database CPU usage has been above 95% for 5 minutes. Query performance degraded.",
        correct_tag="urgent",
        reason="System alert requiring immediate investigation"
    )
    add_example(
        subject="Summary of last week's sprint",
        body="Here's a quick summary of what we shipped last week. No action needed — just sharing for visibility.",
        correct_tag="fyi",
        reason="Sprint summary shared for information only"
    )

    print("\n✅ Done. Listing all examples:\n")
    list_examples()

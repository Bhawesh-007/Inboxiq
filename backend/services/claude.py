import anthropic
import json
from config import CLAUDE_API_KEY

client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

def classify_email(subject: str, sender: str):
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": f"""Classify this email into exactly one label.
                
Subject: {subject}
From: {sender}

Respond with ONLY one word — either: urgent, deadline, action, fyi, or spam"""
            }
        ]
    )
    label = message.content[0].text.strip().lower()
    if label not in ["urgent", "deadline", "action", "fyi", "spam"]:
        label = "fyi"
    return label
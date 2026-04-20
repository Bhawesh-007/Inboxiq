
# services/parser.py
import base64

def extract_body(payload):
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/html":
                data = part.get("body", {}).get("data")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        for part in payload["parts"]:
            result = extract_body(part)
            if result:
                return result

    elif payload.get("mimeType") == "text/html":
        data = payload.get("body", {}).get("data")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

    return ""


def extract_plain_text(payload):
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        for part in payload["parts"]:
            result = extract_plain_text(part)
            if result:
                return result

    elif payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

    return ""
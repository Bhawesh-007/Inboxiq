
# services/parser.py
import base64
from typing import List
from bs4 import BeautifulSoup

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
def extract_headings_and_paragraphs(html: str) -> List[str]:
    """
    Pull out the visible text inside all heading (h1‑h6) and paragraph (p) tags
    from an HTML snippet.
    Parameters
    ----------
    html: str
        A raw HTML string – e.g. the ``body`` field you stored in `data.txt`.
    Returns
    -------
    List[str]
        A list where each entry is the stripped text of one heading or paragraph,
        **preserving order** as it appears in the document.
    Example
    -------
    >>> html = "<h1>Welcome</h1><p>Hello <b>world</b></p>"
    >>> extract_headings_and_paragraphs(html)
    ['Welcome', 'Hello world']
    """
    # Guard against empty / None inputs
    if not html:
        return []
    # Initialise BeautifulSoup – we only need the parser, no network calls.
    soup = BeautifulSoup(html, "html.parser")
    # Find all heading and paragraph tags in document order.
    # The CSS selector "h1, h2, h3, h4, h5, h6, p" respects the original flow.
    elements = soup.select("h1, h2, h3, h4, h5, h6, p")
    # Extract and clean the text for each element.
    # `get_text(strip=True)` collapses whitespace and drops surrounding spaces.
    extracted = [el.get_text(strip=True) for el in elements if el.get_text(strip=True)]
    return extracted
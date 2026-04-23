#this would be my nlp calassfier for dfferent type of emails 
import spacy

nlp = spacy.load("en_core_web_sm")

# keyword rules for each label
LABEL_KEYWORDS = {
    "spam": [
        "offer", "win", "free", "discount", "deal", "prize", "click here",
        "unsubscribe", "promotion", "sale", "% off", "limited time", "congratulations"
    ],
    "urgent": [
        "urgent", "immediate", "asap", "critical", "emergency", "important",
        "action required", "response needed", "immediately"
    ],
    "deadline": [
        "deadline", "due", "by tomorrow", "due date", "submit", "last date",
        "expires", "expiry", "before", "by monday", "by friday", "overdue"
    ],
    "action": [
        "please", "kindly", "request", "confirm", "verify", "update",
        "complete", "fill", "review", "approve", "sign", "respond"
    ],
}

def classify_email(subject: str, sender: str) -> str:
    text = f"{subject} {sender}".lower()
    doc = nlp(text)
    
    # score each label
    scores = {label: 0 for label in LABEL_KEYWORDS}
    
    for label, keywords in LABEL_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                scores[label] += 1
    
    # get label with highest score
    best_label = max(scores, key=scores.get)
    
    # if no keywords matched at all, default to fyi
    if scores[best_label] == 0:
        return "fyi"
    
    return best_label
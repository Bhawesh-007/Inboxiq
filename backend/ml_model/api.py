# model_py/api.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from predict import classify_email, classify_batch

app = Flask(__name__)
CORS(app)


# ── Health check ─────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model": "llama3"})


# ── Classify single email ─────────────────────────────────────

@app.route("/classify", methods=["POST"])
def classify():
    """
    POST /classify
    Body: { "subject": "...", "body": "..." }
    Returns: { "tag": "urgent|action|fyi|spam", "reason": "..." }
    """
    data = request.get_json()

    if not data or not data.get("subject"):
        return jsonify({"error": "subject is required"}), 400

    result = classify_email(
        subject=data["subject"],
        body=data.get("body", "")
    )
    return jsonify(result)


# ── Classify batch of emails ──────────────────────────────────

@app.route("/classify/batch", methods=["POST"])
def batch():
    """
    POST /classify/batch
    Body: { "emails": [{"subject": "...", "body": "..."}, ...] }
    Returns: { "results": [...emails with tag and reason added] }
    """
    data = request.get_json()

    if not data or not isinstance(data.get("emails"), list):
        return jsonify({"error": "emails array is required"}), 400

    if len(data["emails"]) > 50:
        return jsonify({"error": "Max 50 emails per batch"}), 400

    results = classify_batch(data["emails"])
    return jsonify({"results": results})


if __name__ == "__main__":
    print("\n🤖 Email Classifier API starting...")
    print("   Model  : llama3")
    print("   Port   : 5001")
    print("   Routes : POST /classify  |  POST /classify/batch  |  GET /health\n")
    app.run(port=5001, debug=True)

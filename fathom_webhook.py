#!/usr/bin/env python3
"""
Fathom Webhook Receiver (Render deployment)
Receives meeting data from Fathom and stores it.

Endpoints:
  POST /webhook/fathom - Receive Fathom webhooks
  GET /meetings - List recent meetings
  GET /meetings/<id> - Get specific meeting
  GET /health - Health check
"""
import os
import hmac
import hashlib
import json
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

WEBHOOK_SECRET = os.environ.get('FATHOM_WEBHOOK_SECRET', '')

# In-memory storage (for Render - use DB for production persistence)
meetings_store = []
MAX_MEETINGS = 100


def verify_signature(payload, signature):
    """Verify Fathom webhook signature."""
    if not WEBHOOK_SECRET:
        print("Warning: No webhook secret configured, skipping verification")
        return True

    try:
        expected = hmac.new(
            WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)
    except Exception as e:
        print(f"Signature verification error: {e}")
        return False


@app.route('/webhook/fathom', methods=['POST'])
def fathom_webhook():
    """Receive webhook from Fathom."""
    # Verify signature
    signature = request.headers.get('X-Fathom-Signature', '')
    if WEBHOOK_SECRET and not verify_signature(request.data, signature):
        print("Invalid webhook signature")
        return jsonify({"error": "Invalid signature"}), 401

    data = request.json
    event_type = data.get('type', 'unknown')

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fathom event: {event_type}")
    print(f"  Raw data keys: {list(data.keys())}")

    # Store the raw event for debugging
    meeting_data = data.get('data', data)

    # Build meeting record
    meeting_record = {
        "id": meeting_data.get('id', f"meeting-{datetime.now().timestamp()}"),
        "event_type": event_type,
        "received_at": datetime.now().isoformat(),
        "title": meeting_data.get('title', meeting_data.get('name', 'Untitled Meeting')),
        "duration_seconds": meeting_data.get('duration', 0),
        "attendees": meeting_data.get('attendees', meeting_data.get('participants', [])),
        "summary": meeting_data.get('summary', ''),
        "action_items": meeting_data.get('action_items', meeting_data.get('actionItems', [])),
        "transcript": meeting_data.get('transcript', ''),
        "recording_url": meeting_data.get('recording_url', meeting_data.get('recordingUrl', '')),
        "raw_data": data  # Store full payload for debugging
    }

    # Add to store
    meetings_store.append(meeting_record)

    # Trim to max size
    while len(meetings_store) > MAX_MEETINGS:
        meetings_store.pop(0)

    print(f"  Stored meeting: {meeting_record['title']}")
    print(f"  Total meetings stored: {len(meetings_store)}")

    return jsonify({"status": "ok", "meeting_id": meeting_record['id']})


@app.route('/meetings', methods=['GET'])
def list_meetings():
    """List recent meetings."""
    # Return without raw_data to keep response small
    return jsonify([
        {k: v for k, v in m.items() if k != 'raw_data'}
        for m in reversed(meetings_store[-20:])
    ])


@app.route('/meetings/<meeting_id>', methods=['GET'])
def get_meeting(meeting_id):
    """Get specific meeting by ID."""
    for m in meetings_store:
        if m['id'] == meeting_id:
            return jsonify(m)
    return jsonify({"error": "Meeting not found"}), 404


@app.route('/meetings/latest', methods=['GET'])
def get_latest():
    """Get the most recent meeting."""
    if meetings_store:
        m = meetings_store[-1]
        return jsonify({k: v for k, v in m.items() if k != 'raw_data'})
    return jsonify({"error": "No meetings yet"}), 404


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "support-memory-webhook",
        "meetings_stored": len(meetings_store),
        "webhook_secret": "configured" if WEBHOOK_SECRET else "NOT SET"
    })


@app.route('/', methods=['GET'])
def index():
    """Root endpoint."""
    return jsonify({
        "service": "Support Memory Webhook Receiver",
        "endpoints": {
            "POST /webhook/fathom": "Receive Fathom webhooks",
            "GET /meetings": "List recent meetings",
            "GET /meetings/latest": "Get most recent meeting",
            "GET /meetings/<id>": "Get specific meeting",
            "GET /health": "Health check"
        },
        "status": "ready"
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5003))
    print("=" * 50)
    print("SUPPORT MEMORY WEBHOOK RECEIVER")
    print("=" * 50)
    print(f"Webhook secret: {'configured' if WEBHOOK_SECRET else 'NOT SET'}")
    print(f"Listening on port {port}")
    print("=" * 50)
    app.run(host='0.0.0.0', port=port, debug=True)

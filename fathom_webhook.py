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

# Import transcript processor for signal extraction
try:
    from transcript_processor import process_meeting
    PROCESSOR_AVAILABLE = True
except ImportError:
    PROCESSOR_AVAILABLE = False
    print("Warning: transcript_processor not available")

# Google Sheets persistence
try:
    from googleapiclient.discovery import build
    from google_auth import get_credentials
    SHEETS_AVAILABLE = True
except ImportError:
    SHEETS_AVAILABLE = False

app = Flask(__name__)

WEBHOOK_SECRET = os.environ.get('FATHOM_WEBHOOK_SECRET', '')

# Meetings log sheet — create one sheet to store all meetings persistently
MEETINGS_SHEET_ID = os.environ.get('MEETINGS_SHEET_ID', '')

# In-memory cache (loaded from Sheets on startup)
meetings_store = []
MAX_MEETINGS = 100


def get_sheets_service():
    if not SHEETS_AVAILABLE:
        return None
    creds = get_credentials()
    if not creds:
        return None
    return build('sheets', 'v4', credentials=creds)


def load_meetings_from_sheets():
    """Load recent meetings from Google Sheets on startup."""
    if not MEETINGS_SHEET_ID:
        return []
    try:
        service = get_sheets_service()
        if not service:
            return []
        result = service.spreadsheets().values().get(
            spreadsheetId=MEETINGS_SHEET_ID,
            range='Meetings!A2:G'
        ).execute()
        rows = result.get('values', [])
        meetings = []
        for row in rows[-MAX_MEETINGS:]:
            if len(row) >= 4:
                meetings.append({
                    'id': row[0] if len(row) > 0 else '',
                    'title': row[1] if len(row) > 1 else '',
                    'received_at': row[2] if len(row) > 2 else '',
                    'attendees': json.loads(row[3]) if len(row) > 3 else [],
                    'summary': row[4] if len(row) > 4 else '',
                    'action_items': json.loads(row[5]) if len(row) > 5 else [],
                    'recording_url': row[6] if len(row) > 6 else '',
                })
        print(f"Loaded {len(meetings)} meetings from Sheets")
        return meetings
    except Exception as e:
        print(f"Could not load meetings from Sheets: {e}")
        return []


def save_meeting_to_sheets(meeting):
    """Append a single meeting row to Google Sheets."""
    if not MEETINGS_SHEET_ID:
        return
    try:
        service = get_sheets_service()
        if not service:
            return
        row = [
            meeting.get('id', ''),
            meeting.get('title', ''),
            meeting.get('received_at', ''),
            json.dumps(meeting.get('attendees', [])),
            meeting.get('summary', '')[:500],
            json.dumps(meeting.get('action_items', [])),
            meeting.get('recording_url', ''),
        ]
        service.spreadsheets().values().append(
            spreadsheetId=MEETINGS_SHEET_ID,
            range='Meetings!A:G',
            valueInputOption='RAW',
            body={'values': [row]}
        ).execute()
        print(f"  Saved meeting to Sheets: {meeting.get('title')}")
    except Exception as e:
        print(f"  Could not save to Sheets: {e}")


# Load existing meetings on startup
meetings_store = load_meetings_from_sheets()


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

    # Add to store and persist to Sheets
    meetings_store.append(meeting_record)
    save_meeting_to_sheets(meeting_record)

    # Trim to max size
    while len(meetings_store) > MAX_MEETINGS:
        meetings_store.pop(0)

    print(f"  Stored meeting: {meeting_record['title']}")
    print(f"  Total meetings stored: {len(meetings_store)}")

    # Process transcript for signals (action items, decisions, etc.)
    if PROCESSOR_AVAILABLE:
        try:
            processed = process_meeting(meeting_record)
            signals = processed.get('signals', {})
            action_count = len(signals.get('actions_for_me', [])) + len(signals.get('follow_ups', []))
            print(f"  Extracted {action_count} action items, {len(signals.get('decisions', []))} decisions")
        except Exception as e:
            print(f"  Processor error: {e}")

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


@app.route('/inbox', methods=['GET'])
def inbox():
    """Get your action items and deadlines from meetings."""
    if not PROCESSOR_AVAILABLE:
        return jsonify({"error": "Processor not available"}), 500

    from transcript_processor import get_my_inbox, summarize_week

    status = request.args.get('status', 'open')
    inbox_items = get_my_inbox(status if status != 'all' else None)
    summary = summarize_week()

    return jsonify({
        "inbox": inbox_items,
        "summary": summary
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
            "GET /inbox": "Your action items and deadlines from meetings",
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

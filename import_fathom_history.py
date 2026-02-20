#!/usr/bin/env python3
"""
Import historical Fathom meetings into support-memory.
Fetches meetings from the last N days and processes them through transcript_processor.
"""

import os
import requests
from datetime import datetime, timedelta
from transcript_processor import process_meeting

FATHOM_API_KEY = os.environ.get('FATHOM_API_KEY', '6lNhTpgGp8K5kiB2S_f-gg.HvITKygpGV9CViELgCATSe7CuPQia9hPobniXS9RPY0')
FATHOM_API_BASE = "https://api.fathom.ai/external/v1"


def fetch_meetings(days_back=30, include_transcript=True):
    """Fetch meetings from Fathom API."""
    created_after = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")

    all_meetings = []
    cursor = None

    while True:
        params = {
            'created_after': created_after,
            'include_summary': 'true',
            'include_action_items': 'true',
            'include_transcript': str(include_transcript).lower(),
        }
        if cursor:
            params['cursor'] = cursor

        response = requests.get(
            f"{FATHOM_API_BASE}/meetings",
            headers={'X-Api-Key': FATHOM_API_KEY},
            params=params,
            timeout=60
        )

        if response.status_code != 200:
            print(f"API error: {response.status_code}")
            print(response.text[:500])
            break

        data = response.json()
        items = data.get('items', [])
        all_meetings.extend(items)

        print(f"  Fetched {len(items)} meetings (total: {len(all_meetings)})")

        cursor = data.get('next_cursor')
        if not cursor:
            break

    return all_meetings


def import_meetings(days_back=30):
    """Import historical meetings into memory."""
    print(f"=== Importing Fathom meetings from last {days_back} days ===")

    # Fetch meetings (without transcript first to see what we have)
    print("\nFetching meeting list...")
    meetings = fetch_meetings(days_back=days_back, include_transcript=False)

    if not meetings:
        print("No meetings found.")
        return

    print(f"\nFound {len(meetings)} meetings. Processing...")

    processed = 0
    action_items_found = 0

    for i, meeting in enumerate(meetings):
        title = meeting.get('title', meeting.get('meeting_title', 'Untitled'))
        created = meeting.get('created_at', '')[:10]

        print(f"\n[{i+1}/{len(meetings)}] {title} ({created})")

        # Get transcript for this meeting if we need it
        recording_id = meeting.get('recording_id')
        transcript = ''

        if recording_id:
            # Fetch transcript separately
            try:
                resp = requests.get(
                    f"{FATHOM_API_BASE}/recordings/{recording_id}/transcript",
                    headers={'X-Api-Key': FATHOM_API_KEY},
                    timeout=60
                )
                if resp.status_code == 200:
                    transcript_data = resp.json()
                    # Transcript may be in different formats
                    if isinstance(transcript_data, str):
                        transcript = transcript_data
                    elif isinstance(transcript_data, dict):
                        transcript = transcript_data.get('transcript', transcript_data.get('text', ''))
                    elif isinstance(transcript_data, list):
                        # May be list of segments
                        transcript = ' '.join([s.get('text', '') for s in transcript_data if isinstance(s, dict)])
            except Exception as e:
                print(f"  Could not fetch transcript: {e}")

        # Build meeting data for processor
        meeting_data = {
            'id': meeting.get('recording_id') or meeting.get('url', '').split('/')[-1],
            'title': title,
            'transcript': transcript,
            'summary': meeting.get('summary', ''),
            'action_items': meeting.get('action_items', []),
            'attendees': [a.get('email', a.get('name', '')) for a in meeting.get('attendees', [])],
            'duration_seconds': meeting.get('duration_seconds', 0),
        }

        # Process through transcript processor
        try:
            result = process_meeting(meeting_data)
            signals = result.get('signals', {})
            actions = len(signals.get('actions_for_me', [])) + len(signals.get('follow_ups', []))

            if actions > 0:
                print(f"  ✓ {actions} action items extracted")
                action_items_found += actions
            else:
                print(f"  ✓ Processed (no action items)")

            processed += 1
        except Exception as e:
            print(f"  ✗ Error: {e}")

    print(f"\n=== Import Complete ===")
    print(f"Processed: {processed}/{len(meetings)} meetings")
    print(f"Action items found: {action_items_found}")


if __name__ == '__main__':
    import sys

    days = 30
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except:
            pass

    import_meetings(days_back=days)

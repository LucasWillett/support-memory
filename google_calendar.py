#!/usr/bin/env python3
"""
Google Calendar integration for Support Memory.
Read today's meetings, check for scheduled events, create events.
"""

from datetime import datetime, timedelta
from googleapiclient.discovery import build
from google_auth import get_credentials


def get_calendar_service():
    """Get authenticated Calendar API service."""
    creds = get_credentials()
    if not creds:
        return None
    return build('calendar', 'v3', credentials=creds)


def get_todays_events():
    """Get all events for today."""
    service = get_calendar_service()
    if not service:
        return []

    # Today's time range
    now = datetime.now()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    try:
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_of_day.isoformat() + 'Z',
            timeMax=end_of_day.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        return [_format_event(e) for e in events]

    except Exception as e:
        print(f"Error fetching calendar: {e}")
        return []


def get_upcoming_events(days=7):
    """Get events for next N days."""
    service = get_calendar_service()
    if not service:
        return []

    now = datetime.now()
    end = now + timedelta(days=days)

    try:
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now.isoformat() + 'Z',
            timeMax=end.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        return [_format_event(e) for e in events]

    except Exception as e:
        print(f"Error fetching calendar: {e}")
        return []


def find_event(query, days_ahead=14):
    """Search for an event by text in title/description."""
    service = get_calendar_service()
    if not service:
        return None

    now = datetime.now()
    end = now + timedelta(days=days_ahead)

    try:
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now.isoformat() + 'Z',
            timeMax=end.isoformat() + 'Z',
            q=query,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        if events:
            return _format_event(events[0])
        return None

    except Exception as e:
        print(f"Error searching calendar: {e}")
        return None


def check_meeting_scheduled(person_name, days_ahead=14):
    """Check if there's a meeting with a specific person scheduled."""
    return find_event(person_name, days_ahead)


def create_event(title, start_time, duration_minutes=30, description='', attendees=None):
    """Create a calendar event."""
    service = get_calendar_service()
    if not service:
        return None

    end_time = start_time + timedelta(minutes=duration_minutes)

    event = {
        'summary': title,
        'description': description,
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': 'America/New_York',
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': 'America/New_York',
        },
    }

    if attendees:
        event['attendees'] = [{'email': a} for a in attendees]

    try:
        created = service.events().insert(calendarId='primary', body=event).execute()
        return _format_event(created)
    except Exception as e:
        print(f"Error creating event: {e}")
        return None


def _format_event(event):
    """Format a calendar event for internal use."""
    start = event.get('start', {})
    end = event.get('end', {})
    start_raw = start.get('dateTime', start.get('date', ''))
    end_raw = end.get('dateTime', end.get('date', ''))

    start_iso = ''
    end_iso = ''
    time_str = ''
    end_time_str = ''
    date_str = ''

    if 'T' in start_raw:
        dt = datetime.fromisoformat(start_raw.replace('Z', '+00:00'))
        time_str = dt.strftime('%I:%M %p').lstrip('0')
        date_str = dt.strftime('%Y-%m-%d')
        start_iso = dt.isoformat()
    else:
        time_str = 'All day'
        date_str = start_raw
        start_iso = start_raw

    if 'T' in end_raw:
        end_dt = datetime.fromisoformat(end_raw.replace('Z', '+00:00'))
        end_time_str = end_dt.strftime('%I:%M %p').lstrip('0')
        end_iso = end_dt.isoformat()
    else:
        end_iso = end_raw

    # Build attendee display names (skip self)
    attendees_display = []
    for a in event.get('attendees', []):
        if a.get('self'):
            continue
        name = a.get('displayName') or a.get('email', '').split('@')[0].replace('.', ' ').title()
        attendees_display.append(name)

    return {
        'id': event.get('id'),
        'title': event.get('summary', 'No title'),
        'date': date_str,
        'time': time_str,
        'end_time': end_time_str,
        'start_iso': start_iso,
        'end_iso': end_iso,
        'description': event.get('description', ''),
        'attendees': [a.get('email', '') for a in event.get('attendees', [])],
        'attendees_display': attendees_display,
        'link': event.get('htmlLink', ''),
        'color_id': event.get('colorId', ''),  # Empty string = calendar default (keep)
    }


if __name__ == '__main__':
    print("=== Today's Calendar ===")
    events = get_todays_events()
    if not events:
        print("No events today (or not authenticated)")
    else:
        for e in events:
            print(f"  {e['time']}: {e['title']}")

    print("\n=== Next 7 Days ===")
    upcoming = get_upcoming_events(7)
    for e in upcoming[:10]:
        print(f"  {e['date']} {e['time']}: {e['title']}")

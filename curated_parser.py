#!/usr/bin/env python3
"""
Smart parser for curated Slack messages.
Extracts meetings, dates, people, and action items from pasted content.
"""

import re
from datetime import datetime, timedelta


# Date patterns
DATE_PATTERNS = [
    # Specific days
    (r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', 'weekday'),
    (r'\b(tomorrow)\b', 'relative'),
    (r'\b(next week)\b', 'relative'),
    (r'\b(this week)\b', 'relative'),
    (r'\b(end of week|eow)\b', 'relative'),
    (r'\b(end of day|eod)\b', 'relative'),
    # Dates with ordinals
    (r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* (\d{1,2})(?:st|nd|rd|th)?\b', 'month_day'),
    (r'\b(\d{1,2})(?:st|nd|rd|th)?\b', 'day_only'),
    # Friday the 20th style
    (r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday) the (\d{1,2})(?:st|nd|rd|th)?\b', 'weekday_date'),
]

# Meeting patterns
MEETING_PATTERNS = [
    r'(?:can we|let\'s|want to|should we) (?:grab|get|schedule|set up|have) (\d+) minutes',
    r'(?:grab|get|schedule) (?:some )?time',
    r'(?:can we|let\'s) (?:sync|meet|chat|talk|connect)',
    r'(?:set up|schedule) a (?:call|meeting|sync)',
    r'(?:20|30|15|45|60) minutes',
    r'quick (?:call|chat|sync)',
]

# People extraction - names following common patterns
PEOPLE_PATTERNS = [
    r'(?:Hey|Hi|Hello),?\s+([A-Z][a-z]{2,})',  # Greetings
    r'(?:bring|include|invite|cc)\s+([A-Z][a-z]{2,})',  # Explicit mentions
    r"I'll bring ([A-Z][a-z]{2,})",  # "I'll bring Hannah"
    r'@([a-z]+(?:\.[a-z]+)?)',  # Slack mentions like @gino.ferrario
]

# Common words that look like names but aren't
FALSE_POSITIVE_NAMES = {
    'the', 'a', 'an', 'this', 'that', 'our', 'my', 'your', 'we', 'i',
    'what', 'when', 'where', 'why', 'how', 'which', 'who',
    'can', 'could', 'would', 'should', 'will', 'may', 'might',
    'let', 'get', 'got', 'have', 'has', 'had',
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
    'january', 'february', 'march', 'april', 'may', 'june',
    'july', 'august', 'september', 'october', 'november', 'december',
    'technical', 'timeline', 'scope', 'automation', 'feasibility',
    'whether', 'since', 'about', 'through', 'spazious', 'cvent',
}

# Topic indicators
TOPIC_PATTERNS = [
    r'(?:about|regarding|re:|discuss|walk through|cover)[:\s]+(.+?)(?:\.|$|\n)',
    r'(?:conversation|meeting|call) (?:about|on|regarding) (.+?)(?:\.|$|\n)',
]


def parse_curated_message(text, note=None):
    """
    Parse a curated message for meetings, dates, and action items.

    Args:
        text: The pasted message content
        note: Optional note from Lucas (e.g., "scheduled for Friday the 20th")

    Returns:
        dict with extracted information
    """
    combined = f"{note or ''}\n{text}".lower()
    original = f"{note or ''}\n{text}"

    result = {
        'has_meeting': False,
        'meeting_date': None,
        'meeting_date_text': None,
        'people': [],
        'topics': [],
        'duration_minutes': None,
        'is_scheduled': False,
        'raw_text': text[:500],
    }

    # Check for meeting indicators
    for pattern in MEETING_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            result['has_meeting'] = True
            break

    # Check if already scheduled
    if any(word in combined for word in ['scheduled', 'booked', 'set up', 'confirmed', 'on the calendar']):
        result['is_scheduled'] = True

    # Extract duration
    duration_match = re.search(r'(\d+)\s*(?:min|minutes)', combined)
    if duration_match:
        result['duration_minutes'] = int(duration_match.group(1))

    # Extract dates - prioritize the note (Lucas's annotation)
    if note:
        date_info = _extract_date(note.lower())
        if date_info:
            result['meeting_date'] = date_info['date']
            result['meeting_date_text'] = date_info['text']

    # Fall back to message content if no date in note
    if not result['meeting_date']:
        date_info = _extract_date(combined)
        if date_info:
            result['meeting_date'] = date_info['date']
            result['meeting_date_text'] = date_info['text']

    # Extract people
    for pattern in PEOPLE_PATTERNS:
        for match in re.finditer(pattern, original):
            name = match.group(1).strip()
            # Filter out common false positives
            if name.lower() not in FALSE_POSITIVE_NAMES:
                if len(name) > 2 and name not in result['people']:
                    result['people'].append(name)

    # Extract topics
    for pattern in TOPIC_PATTERNS:
        match = re.search(pattern, combined)
        if match:
            topic = match.group(1).strip()[:100]
            if len(topic) > 5:
                result['topics'].append(topic)

    # Look for bullet points as potential topics
    bullets = re.findall(r'[•\-\*]\s*(.+?)(?:\n|$)', text)
    for bullet in bullets[:5]:  # Max 5 bullets
        if len(bullet) > 5 and len(bullet) < 100:
            result['topics'].append(bullet.strip())

    return result


def _extract_date(text):
    """Extract a date from text and return both the date object and original text."""
    today = datetime.now()

    # "Friday the 20th" pattern
    match = re.search(r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday) the (\d{1,2})(?:st|nd|rd|th)?', text)
    if match:
        weekday_name = match.group(1)
        day = int(match.group(2))
        # Find the next occurrence of this weekday with this day number
        target_date = _find_date_with_day(day, weekday_name)
        if target_date:
            return {'date': target_date, 'text': match.group(0)}

    # "the 20th" pattern
    match = re.search(r'the (\d{1,2})(?:st|nd|rd|th)?', text)
    if match:
        day = int(match.group(1))
        # Assume current or next month
        try:
            target = today.replace(day=day)
            if target < today:
                # Next month
                if today.month == 12:
                    target = today.replace(year=today.year + 1, month=1, day=day)
                else:
                    target = today.replace(month=today.month + 1, day=day)
            return {'date': target.strftime('%Y-%m-%d'), 'text': match.group(0)}
        except ValueError:
            pass

    # Weekday names
    weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    for i, day_name in enumerate(weekdays):
        if day_name in text:
            # Find next occurrence of this weekday
            days_ahead = i - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            target = today + timedelta(days=days_ahead)
            return {'date': target.strftime('%Y-%m-%d'), 'text': day_name}

    # Tomorrow
    if 'tomorrow' in text:
        target = today + timedelta(days=1)
        return {'date': target.strftime('%Y-%m-%d'), 'text': 'tomorrow'}

    # This week / next week
    if 'next week' in text:
        target = today + timedelta(days=7)
        return {'date': target.strftime('%Y-%m-%d'), 'text': 'next week'}

    if 'this week' in text:
        # End of this week (Friday)
        days_until_friday = (4 - today.weekday()) % 7
        if days_until_friday == 0:
            days_until_friday = 7
        target = today + timedelta(days=days_until_friday)
        return {'date': target.strftime('%Y-%m-%d'), 'text': 'this week'}

    return None


def _find_date_with_day(day, weekday_name):
    """Find the next date that has both the specified day number and weekday."""
    weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    target_weekday = weekdays.index(weekday_name.lower())

    today = datetime.now()

    # Check next 60 days
    for i in range(60):
        check_date = today + timedelta(days=i)
        if check_date.day == day and check_date.weekday() == target_weekday:
            return check_date.strftime('%Y-%m-%d')

    return None


def create_inbox_item(parsed, source='curated'):
    """Create an inbox item from parsed message."""
    if not parsed['has_meeting']:
        return None

    # Build description
    desc_parts = []
    if parsed['people']:
        desc_parts.append(f"With: {', '.join(parsed['people'])}")
    if parsed['topics']:
        desc_parts.append(f"Topics: {'; '.join(parsed['topics'][:3])}")
    if parsed['duration_minutes']:
        desc_parts.append(f"Duration: {parsed['duration_minutes']} min")

    return {
        'type': 'meeting',
        'date_added': datetime.now().strftime('%Y-%m-%d'),
        'meeting_date': parsed['meeting_date'],
        'meeting_date_text': parsed['meeting_date_text'],
        'people': parsed['people'],
        'topics': parsed['topics'],
        'content': ' | '.join(desc_parts) if desc_parts else parsed['raw_text'][:100],
        'status': 'scheduled' if parsed['is_scheduled'] else 'pending',
        'source': source,
    }


# Test
if __name__ == '__main__':
    test_message = """Hey Gino—

Heard the Cvent conversation went well. Congrats on getting them on board with the Spazious acquisition. Kevin mentioned you're looking at a pre-API automation process. I want to make sure we're on the same page about what that looks like and whether it makes sense.

Can we grab 20 minutes this week? I'll bring Hannah since she's our project lead, and we can walk through:

• What you're envisioning for the automation
• Technical feasibility and timeline
• Scope (projected # of customers)

Let me know!"""

    test_note = "scheduled meeting for Friday the 20th"

    result = parse_curated_message(test_message, test_note)

    print("=== Parsed Result ===")
    print(f"Has meeting: {result['has_meeting']}")
    print(f"Is scheduled: {result['is_scheduled']}")
    print(f"Date: {result['meeting_date']} ({result['meeting_date_text']})")
    print(f"Duration: {result['duration_minutes']} minutes")
    print(f"People: {result['people']}")
    print(f"Topics: {result['topics']}")

    print("\n=== Inbox Item ===")
    item = create_inbox_item(result)
    if item:
        for k, v in item.items():
            print(f"  {k}: {v}")

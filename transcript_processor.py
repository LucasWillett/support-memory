#!/usr/bin/env python3
"""
Transcript Processor - Extract actionable signals from meeting transcripts.
Personal second brain for staying sharp and never forgetting important things.

Extracts:
- Action items assigned to you
- Decisions made
- Commitments from others
- Customer/project mentions
- Follow-ups needed
- Deadlines and dates
"""

import re
from datetime import datetime
from shared_memory import load_memory, save_memory, load_entities

# Your name variations (for detecting action items assigned to you)
MY_NAMES = ['lucas', 'luke', 'support', 'support team']

# Direct reports - track their wellness signals from meetings
DIRECT_REPORTS = {
    'christian': ['christian', 'christian staley'],
    'hannah': ['hannah', 'hannah holbrook'],
}

# Stress indicators in speech patterns
STRESS_PATTERNS = [
    r'\b(overwhelmed|swamped|drowning|slammed|buried)\b',
    r'\b(frustrated|annoying|annoyed|struggling)\b',
    r'\b(worried|concerned|anxious|stressed)\b',
    r"\b(can't keep up|too much|falling behind|behind on)\b",
    r'\b(exhausted|tired|burnt out|burning out)\b',
]

# Positive indicators
POSITIVE_PATTERNS = [
    r'\b(excited|looking forward|enjoying|proud)\b',
    r'\b(good progress|on track|ahead of|nailed|crushed)\b',
    r'\b(feeling good|going well|things are good)\b',
]

# Signal patterns
PATTERNS = {
    # Action items for you
    'action_for_me': [
        r'lucas[,:]?\s+can you\s+(.+?)(?:\.|$|\?)',
        r'lucas[,:]?\s+(?:will you|could you|would you)\s+(.+?)(?:\.|$|\?)',
        r'lucas[,:]?\s+(?:please|pls)\s+(.+?)(?:\.|$)',
        r'support\s+(?:needs to|should|will|to)\s+(.+?)(?:\.|$)',
        r'can\s+(?:lucas|support)\s+(.+?)(?:\.|$|\?)',
        r'(?:lucas|luke)[,:]?\s+(?:follow up|look into|check on|handle|take care of)\s+(.+?)(?:\.|$)',
        r'(?:assign(?:ed)?|task(?:ed)?)\s+(?:to\s+)?lucas[:\s]+(.+?)(?:\.|$)',
    ],

    # Decisions made
    'decision': [
        r"(?:we(?:'ve)?|let's)\s+decided?\s+(?:to\s+)?(.+?)(?:\.|$)",
        r"decision[:\s]+(.+?)(?:\.|$)",
        r"(?:we're|we are)\s+going\s+(?:to|with)\s+(.+?)(?:\.|$)",
        r"(?:final|agreed)[:\s]+(.+?)(?:\.|$)",
        r"(?:the plan is|plan is to)\s+(.+?)(?:\.|$)",
    ],

    # Commitments from others
    'commitment': [
        r"i(?:'ll| will)\s+(?:get|send|share|provide|follow up|check|look into)\s+(.+?)(?:\.|$)",
        r"i(?:'ll| will)\s+have\s+(?:that|this|it)\s+(.+?)(?:\.|$)",
        r"(?:i can|i'll)\s+(.+?)\s+by\s+(.+?)(?:\.|$)",
        r"let me\s+(.+?)(?:\.|$)",
        r"i(?:'ll| will)\s+circle back\s+(?:on\s+)?(.+?)(?:\.|$)",
    ],

    # Follow-ups needed
    'follow_up': [
        r"(?:let's|we should|need to)\s+(?:circle back|follow up|revisit)\s+(?:on\s+)?(.+?)(?:\.|$)",
        r"(?:follow up|following up)\s+(?:on|about|with)\s+(.+?)(?:\.|$)",
        r"(?:don't forget|remember)\s+(?:to\s+)?(.+?)(?:\.|$)",
        r"(?:next steps?|action items?)[:\s]+(.+?)(?:\.|$)",
        r"(?:to do|todo)[:\s]+(.+?)(?:\.|$)",
    ],

    # Deadlines and dates
    'deadline': [
        r"by\s+(end of (?:day|week|month)|eod|eow|eom|friday|monday|tomorrow|next week)(?:\.|,|$)",
        r"(?:due|deadline)[:\s]+(.+?)(?:\.|$)",
        r"(?:need|needs)\s+(?:to be|this)\s+(?:done|ready|completed)\s+by\s+(.+?)(?:\.|$)",
        r"before\s+(launch|release|go[- ]live|the meeting|monday|friday)(?:\.|,|$)",
    ],

    # Blockers and issues
    'blocker': [
        r"(?:blocked|waiting)\s+(?:on|for)\s+(.+?)(?:\.|$)",
        r"(?:can't|cannot)\s+(?:proceed|move forward|continue)\s+(?:until|without)\s+(.+?)(?:\.|$)",
        r"(?:dependency|dependencies)[:\s]+(.+?)(?:\.|$)",
        r"(?:need|needs)\s+(.+?)\s+(?:first|before)(?:\.|$)",
    ],

    # Customer mentions (will cross-reference with entities)
    'customer_mention': [
        r"(?:customer|client|account)[:\s]+(.+?)(?:\.|,|$)",
        r"(?:talking to|meeting with|call with)\s+(.+?)(?:\.|$)",
    ],

    # Project/feature mentions
    'project_mention': [
        r"(?:project|feature|initiative)[:\s]+(.+?)(?:\.|,|$)",
        r"(?:working on|building|shipping)\s+(.+?)(?:\.|$)",
        r"(?:truetour|embed|beta|migration|launch|rollout)\s+(.+?)(?:\.|$)",
    ],
}

# Known project keywords to watch for
PROJECT_KEYWORDS = [
    'truetour', 'embed', 'integration', 'api', 'webhook',
    'beta', 'pilot', 'migration', 'rollout', 'launch',
    'dashboard', 'reporting', 'analytics', 'automation',
]


def extract_signals(transcript, meeting_title=''):
    """
    Extract actionable signals from a meeting transcript.
    Returns dict of categorized signals.
    """
    # Always return a properly structured dict
    signals = {
        'actions_for_me': [],
        'decisions': [],
        'commitments': [],
        'follow_ups': [],
        'deadlines': [],
        'blockers': [],
        'customers_mentioned': [],
        'projects_mentioned': [],
    }

    if not transcript:
        return signals

    text = str(transcript).lower()

    # Load known entities for cross-referencing
    entities = load_entities()
    known_customers = [c.lower() for c in entities.get('customers', {}).keys()]

    # Extract each signal type
    for pattern in PATTERNS['action_for_me']:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            action = match.group(1).strip()
            if action and len(action) > 5:
                signals['actions_for_me'].append(action)

    for pattern in PATTERNS['decision']:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            decision = match.group(1).strip()
            if decision and len(decision) > 5:
                signals['decisions'].append(decision)

    for pattern in PATTERNS['commitment']:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            commitment = match.group(1).strip()
            if commitment and len(commitment) > 5:
                signals['commitments'].append(commitment)

    for pattern in PATTERNS['follow_up']:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            follow_up = match.group(1).strip()
            if follow_up and len(follow_up) > 5:
                signals['follow_ups'].append(follow_up)

    for pattern in PATTERNS['deadline']:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            deadline = match.group(1).strip()
            if deadline:
                signals['deadlines'].append(deadline)

    for pattern in PATTERNS['blocker']:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            blocker = match.group(1).strip()
            if blocker and len(blocker) > 5:
                signals['blockers'].append(blocker)

    # Find known customers mentioned
    for customer in known_customers:
        if customer in text:
            signals['customers_mentioned'].append(customer)

    # Find project keywords
    for project in PROJECT_KEYWORDS:
        if project in text:
            signals['projects_mentioned'].append(project)

    # Deduplicate
    for key in signals:
        signals[key] = list(set(signals[key]))

    return signals


def extract_team_wellness(transcript, attendees=None):
    """
    Extract wellness signals for direct reports from meeting transcript.
    Returns dict of {person: {stress_signals, positive_signals, topics}}.
    """
    if not transcript:
        return {}

    text = str(transcript).lower()
    attendees_lower = [a.lower() for a in (attendees or [])]

    team_signals = {}

    for person_key, names in DIRECT_REPORTS.items():
        # Check if this person was in the meeting
        person_in_meeting = any(name in attendees_lower or name in text[:500] for name in names)

        if not person_in_meeting:
            continue

        signals = {
            'stress': [],
            'positive': [],
            'blockers': [],
        }

        # Look for stress patterns
        for pattern in STRESS_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            signals['stress'].extend(matches)

        # Look for positive patterns
        for pattern in POSITIVE_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            signals['positive'].extend(matches)

        # Look for blockers they raised
        blocker_patterns = [
            r"(?:i'm|i am) (?:blocked|waiting) on (.+?)(?:\.|$)",
            r"(?:can't|cannot) (?:proceed|move forward) (?:until|without) (.+?)(?:\.|$)",
        ]
        for pattern in blocker_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                signals['blockers'].append(match.group(1).strip()[:100])

        # Calculate overall sentiment
        stress_count = len(signals['stress'])
        positive_count = len(signals['positive'])

        if stress_count > positive_count + 2:
            signals['sentiment'] = 'stressed'
        elif positive_count > stress_count + 2:
            signals['sentiment'] = 'positive'
        else:
            signals['sentiment'] = 'neutral'

        team_signals[person_key] = signals

    return team_signals


def log_team_wellness_from_meeting(team_signals, meeting_title):
    """Log team wellness signals from a meeting to memory."""
    if not team_signals:
        return

    try:
        from team_wellness import log_team_update
    except ImportError:
        return

    for person, signals in team_signals.items():
        if signals['sentiment'] != 'neutral' or signals['blockers']:
            content_parts = [f"From: {meeting_title}"]
            if signals['sentiment'] == 'stressed':
                content_parts.append(f"Seemed stressed ({len(signals['stress'])} stress signals)")
            elif signals['sentiment'] == 'positive':
                content_parts.append(f"Seemed positive ({len(signals['positive'])} positive signals)")
            if signals['blockers']:
                content_parts.append(f"Blockers: {signals['blockers'][0]}")

            mood = 2 if signals['sentiment'] == 'stressed' else 4 if signals['sentiment'] == 'positive' else 3

            log_team_update(
                person=person,
                update_type='meeting',
                content=' | '.join(content_parts),
                mood=mood
            )


def process_meeting(meeting_data):
    """
    Process a meeting from Fathom webhook and store extracted signals.

    meeting_data should have:
    - title: meeting title
    - transcript: full transcript text
    - summary: meeting summary (if available)
    - action_items: Fathom's extracted action items (if available)
    - attendees: list of attendees
    - duration_seconds: meeting length
    - id: meeting ID
    """
    title = meeting_data.get('title', 'Untitled Meeting')
    transcript = meeting_data.get('transcript', '')
    summary = meeting_data.get('summary', '')
    fathom_actions = meeting_data.get('action_items', [])

    # Ensure transcript and summary are strings
    if isinstance(transcript, list):
        transcript = ' '.join([str(t) for t in transcript])
    if isinstance(transcript, dict):
        transcript = transcript.get('text', str(transcript))
    if isinstance(summary, list):
        summary = ' '.join([str(s) for s in summary])
    if isinstance(summary, dict):
        summary = summary.get('text', summary.get('summary', str(summary)))

    # Initialize empty signals - use Fathom's extracted items only
    signals = {
        'actions_for_me': [],
        'decisions': [],
        'commitments': [],
        'follow_ups': [],
        'deadlines': [],
        'blockers': [],
        'customers_mentioned': [],
        'projects_mentioned': [],
    }

    # Use Fathom's action items - filter to only items assigned to Lucas
    my_names = ['lucas', 'luke', 'lucas willett', 'lucaswillett']
    my_emails = ['lucas@visitingmedia.com', 'lucas.willett@']

    if fathom_actions:
        if isinstance(fathom_actions, list):
            for item in fathom_actions:
                action_text = None
                is_mine = False

                if isinstance(item, str) and len(item) > 10:
                    action_text = item
                    is_mine = True  # No assignee info, include it
                elif isinstance(item, dict):
                    action_text = item.get('text') or item.get('content') or item.get('description')

                    # Check assignee
                    assignee = item.get('assignee', {})
                    if assignee:
                        assignee_name = (assignee.get('name') or '').lower()
                        assignee_email = (assignee.get('email') or '').lower()

                        # Check if assigned to me
                        if any(n in assignee_name for n in my_names):
                            is_mine = True
                        if any(e in assignee_email for e in my_emails):
                            is_mine = True
                    else:
                        # No assignee specified - might be general, skip it
                        is_mine = False

                # Filter out garbage and only include mine
                if is_mine and action_text and len(action_text) > 10 and len(action_text) < 500:
                    if '{' not in action_text and 'speaker' not in action_text.lower():
                        signals['follow_ups'].append(action_text.strip())

    # Build meeting record for memory
    meeting_record = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'time': datetime.now().strftime('%H:%M'),
        'title': title,
        'meeting_id': meeting_data.get('id'),
        'duration_minutes': round(meeting_data.get('duration_seconds', 0) / 60),
        'attendees': meeting_data.get('attendees', []),
        'signals': signals,
        'summary': summary[:500] if summary else '',
        'has_actions': bool(signals['actions_for_me'] or signals['follow_ups']),
    }

    # Extract team wellness signals from meetings with direct reports
    attendees = meeting_data.get('attendees', [])
    team_signals = extract_team_wellness(transcript, attendees)
    if team_signals:
        meeting_record['team_wellness'] = team_signals
        log_team_wellness_from_meeting(team_signals, title)

    # Store in memory
    mem = load_memory()

    if 'meetings' not in mem:
        mem['meetings'] = []

    mem['meetings'].append(meeting_record)

    # Keep last 50 meetings
    mem['meetings'] = mem['meetings'][-50:]

    # Add action items and follow-ups to Google Tasks (source of truth)
    try:
        from google_tasks import create_task
        action_items = signals['actions_for_me'] + signals['follow_ups']
        for action in action_items:
            create_task(
                title=action[:500],
                notes=f"From meeting: {title} ({meeting_record['date']})"
            )
        for deadline in signals['deadlines']:
            create_task(
                title=deadline[:500],
                notes=f"Deadline from: {title} ({meeting_record['date']})"
            )
    except Exception as e:
        print(f"  Could not write to Google Tasks: {e}")

    # Also keep inbox in memory.json for legacy reference
    if signals['actions_for_me'] or signals['follow_ups'] or signals['deadlines'] or signals['blockers']:
        if 'inbox' not in mem:
            mem['inbox'] = []

        for action in signals['actions_for_me']:
            mem['inbox'].append({
                'type': 'action',
                'from_meeting': title,
                'date': meeting_record['date'],
                'content': action,
                'status': 'open',
            })

        for action in signals['follow_ups']:
            mem['inbox'].append({
                'type': 'action',
                'from_meeting': title,
                'date': meeting_record['date'],
                'content': action,
                'status': 'open',
            })

        for deadline in signals['deadlines']:
            mem['inbox'].append({
                'type': 'deadline',
                'from_meeting': title,
                'date': meeting_record['date'],
                'content': deadline,
                'status': 'open',
            })

        mem['inbox'] = mem['inbox'][-100:]

    save_memory(mem)

    return meeting_record


def get_my_inbox(status='open'):
    """Get action items and deadlines from inbox."""
    mem = load_memory()
    inbox = mem.get('inbox', [])

    if status:
        inbox = [i for i in inbox if i.get('status') == status]

    return inbox


def get_recent_meetings(days=7):
    """Get meetings from last N days."""
    mem = load_memory()
    meetings = mem.get('meetings', [])

    cutoff = datetime.now().strftime('%Y-%m-%d')
    # Simple filter - could be smarter with date math
    return meetings[-20:]  # Last 20 meetings as approximation


def summarize_week():
    """Generate a summary of the week's meetings and action items."""
    mem = load_memory()
    meetings = mem.get('meetings', [])[-10:]  # Last 10 meetings
    inbox = [i for i in mem.get('inbox', []) if i.get('status') == 'open']

    summary = {
        'meetings_count': len(meetings),
        'open_actions': len([i for i in inbox if i['type'] == 'action']),
        'upcoming_deadlines': len([i for i in inbox if i['type'] == 'deadline']),
        'customers_discussed': [],
        'projects_discussed': [],
        'key_decisions': [],
    }

    for m in meetings:
        signals = m.get('signals', {})
        summary['customers_discussed'].extend(signals.get('customers_mentioned', []))
        summary['projects_discussed'].extend(signals.get('projects_mentioned', []))
        summary['key_decisions'].extend(signals.get('decisions', []))

    # Deduplicate
    summary['customers_discussed'] = list(set(summary['customers_discussed']))
    summary['projects_discussed'] = list(set(summary['projects_discussed']))

    return summary


# CLI for testing
if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--inbox':
        print("=== YOUR INBOX ===")
        inbox = get_my_inbox()
        if not inbox:
            print("No open items!")
        for item in inbox:
            print(f"[{item['type'].upper()}] {item['content']}")
            print(f"  From: {item['from_meeting']} ({item['date']})")
            print()

    elif len(sys.argv) > 1 and sys.argv[1] == '--summary':
        print("=== WEEK SUMMARY ===")
        s = summarize_week()
        print(f"Meetings: {s['meetings_count']}")
        print(f"Open actions: {s['open_actions']}")
        print(f"Deadlines: {s['upcoming_deadlines']}")
        print(f"Customers: {', '.join(s['customers_discussed']) or 'None'}")
        print(f"Projects: {', '.join(s['projects_discussed']) or 'None'}")
        if s['key_decisions']:
            print("\nKey decisions:")
            for d in s['key_decisions'][:5]:
                print(f"  - {d}")

    else:
        print("Transcript Processor - Personal Meeting Memory")
        print()
        print("Usage:")
        print("  python3 transcript_processor.py --inbox    # Show open action items")
        print("  python3 transcript_processor.py --summary  # Week summary")
        print()
        print("This module is called automatically by fathom_webhook.py")
        print("when new meeting data arrives.")

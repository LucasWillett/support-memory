#!/usr/bin/env python3
"""
Heartbeat & Quick Capture System

Two functions:
1. Quick Capture: Monitor #lucas-briefing for brain dumps / paper notes
   - Parse items, organize in memory, create Google Tasks
   - Trigger with "capture:" or "notes:" or bullet points

2. Heartbeat: Daily check-in with status and prompt for input
   - Posts to #lucas-briefing
   - Shows pending tasks, recent activity
   - Prompts: "Anything from your paper notes?"
"""

import os
import re
from datetime import datetime, timedelta
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from shared_memory import load_memory, save_memory
from google_tasks import create_task, get_all_open_tasks, format_for_briefing

# Config
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
BRIEFING_CHANNEL = "C0AFPAQ0KMF"  # #lucas-briefing
LUCAS_USER_ID = "U9NLNTPDK"

client = WebClient(token=SLACK_BOT_TOKEN)


def parse_capture(text):
    """Parse a brain dump / paper notes capture into actionable items.

    Returns list of items with type (task, note, idea) and content.
    """
    items = []

    # Split by newlines and common bullet patterns
    lines = re.split(r'\n|•|◦|▪|►|-(?=\s)', text)

    for line in lines:
        line = line.strip()
        if not line or len(line) < 3:
            continue

        # Skip the trigger words
        if line.lower() in ['capture:', 'notes:', 'brain dump:', 'paper notes:']:
            continue

        item = {'raw': line, 'type': 'note', 'content': line}

        # Detect tasks (action words, deadlines)
        task_patterns = [
            r'^(todo|task|do|need to|must|should|follow up|schedule|call|email|send|review|check|update|create|build|fix|finish)[\s:]+',
            r'(by|due|before|deadline)\s+(monday|tuesday|wednesday|thursday|friday|tomorrow|eod|eow|next week|\d{1,2}[/-]\d{1,2})',
        ]
        for pattern in task_patterns:
            if re.search(pattern, line.lower()):
                item['type'] = 'task'
                break

        # Detect ideas
        idea_patterns = [
            r'^(idea|maybe|could|what if|consider|explore|look into|research)',
        ]
        for pattern in idea_patterns:
            if re.search(pattern, line.lower()):
                item['type'] = 'idea'
                break

        # Extract due date if present
        due_match = re.search(r'(by|due|before)\s+(monday|tuesday|wednesday|thursday|friday|tomorrow|eod|eow|\d{1,2}[/-]\d{1,2})', line.lower())
        if due_match:
            item['due_hint'] = due_match.group(2)

        items.append(item)

    return items


def process_capture(text, user_id):
    """Process a capture, create tasks, store in memory."""
    items = parse_capture(text)

    if not items:
        return "Couldn't parse any items from that. Try bullet points or one item per line."

    tasks_created = 0
    notes_stored = 0
    ideas_stored = 0

    mem = load_memory()
    if 'captures' not in mem:
        mem['captures'] = []

    capture_entry = {
        'date': datetime.now().isoformat(),
        'user': user_id,
        'items': [],
    }

    for item in items:
        if item['type'] == 'task':
            # Create Google Task
            result = create_task(
                title=item['content'][:100],
                notes=f"Captured from paper notes on {datetime.now().strftime('%Y-%m-%d')}"
            )
            if result:
                tasks_created += 1
                item['google_task_id'] = result.get('id')
        elif item['type'] == 'idea':
            ideas_stored += 1
        else:
            notes_stored += 1

        capture_entry['items'].append(item)

    # Store in memory
    mem['captures'].append(capture_entry)
    mem['captures'] = mem['captures'][-50:]  # Keep last 50 captures
    save_memory(mem)

    # Build response
    response = f"*Captured {len(items)} items:*\n"
    if tasks_created:
        response += f"• {tasks_created} task(s) → Google Tasks\n"
    if ideas_stored:
        response += f"• {ideas_stored} idea(s) → Memory\n"
    if notes_stored:
        response += f"• {notes_stored} note(s) → Memory\n"

    return response


def send_heartbeat():
    """Send daily heartbeat check-in to #lucas-briefing."""

    # Get current tasks
    tasks = get_all_open_tasks()
    task_count = len(tasks)

    # Get recent captures
    mem = load_memory()
    recent_captures = mem.get('captures', [])[-3:]

    # Build message
    msg = f"*Daily Check-in*\n\n"

    # Task summary
    if task_count > 0:
        msg += f"*Open Tasks:* {task_count}\n"
        # Show top 3 by due date
        for task in tasks[:3]:
            due = f" (due: {task['due']})" if task['due'] else ""
            msg += f"  • {task['title'][:50]}{due}\n"
        if task_count > 3:
            msg += f"  _...and {task_count - 3} more_\n"
    else:
        msg += "*Open Tasks:* None\n"

    msg += "\n"

    # Prompt for paper notes
    msg += "*Quick Capture:*\n"
    msg += "Got paper notes? Drop them here with `capture:` or just bullet points:\n"
    msg += "```\ncapture:\n- Call Mike about Q1\n- Idea: automate the weekly report\n- Review PR by Friday\n```\n"
    msg += "I'll sort them and add tasks to Google Tasks.\n"

    try:
        client.chat_postMessage(
            channel=BRIEFING_CHANNEL,
            text=msg
        )
        print(f"Heartbeat sent at {datetime.now().strftime('%H:%M')}")
        return True
    except SlackApiError as e:
        print(f"Error sending heartbeat: {e}")
        return False


class CaptureMonitor:
    """Monitor #lucas-briefing for capture requests."""

    def __init__(self):
        self.processed_messages = set()

    def check_for_captures(self):
        """Check for new capture requests."""
        try:
            result = client.conversations_history(
                channel=BRIEFING_CHANNEL,
                limit=10
            )

            for msg in result.get('messages', []):
                msg_ts = msg.get('ts')
                text = msg.get('text', '')
                user = msg.get('user', '')

                if msg_ts in self.processed_messages:
                    continue
                if msg.get('bot_id'):
                    continue

                self.processed_messages.add(msg_ts)

                # Check for capture triggers
                is_capture = False
                text_lower = text.lower()

                if any(trigger in text_lower for trigger in ['capture:', 'notes:', 'brain dump:', 'paper notes:']):
                    is_capture = True
                elif text.strip().startswith('-') or text.strip().startswith('•'):
                    # Bullet points might be a capture
                    if '\n' in text or len(text.split('-')) > 2:
                        is_capture = True

                if is_capture and user == LUCAS_USER_ID:
                    print(f"Processing capture from {user}")
                    response = process_capture(text, user)

                    # Reply in thread
                    client.chat_postMessage(
                        channel=BRIEFING_CHANNEL,
                        thread_ts=msg_ts,
                        text=response
                    )

        except SlackApiError as e:
            print(f"Error checking for captures: {e}")


def run_capture_monitor(poll_interval=10):
    """Run continuous capture monitor."""
    import time

    print("=" * 50)
    print("CAPTURE MONITOR")
    print("=" * 50)
    print(f"Channel: #lucas-briefing")
    print(f"Triggers: 'capture:', 'notes:', bullet points")
    print("-" * 50)

    monitor = CaptureMonitor()

    # Skip existing messages
    try:
        result = client.conversations_history(channel=BRIEFING_CHANNEL, limit=20)
        for msg in result.get('messages', []):
            monitor.processed_messages.add(msg.get('ts'))
        print(f"Skipped {len(monitor.processed_messages)} existing messages")
    except:
        pass

    print("Listening for captures...")

    while True:
        try:
            monitor.check_for_captures()
            time.sleep(poll_interval)
        except KeyboardInterrupt:
            print("\nMonitor stopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(poll_interval)


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == 'heartbeat':
            send_heartbeat()
        elif cmd == 'monitor':
            run_capture_monitor()
        elif cmd == 'test':
            # Test capture parsing
            test_input = """capture:
            - Call Mike about Q1 planning
            - Idea: automate weekly report
            - Review Hannah's PR by Friday
            - Check on Granola integration
            - Todo: send invoice to accounting
            """
            items = parse_capture(test_input)
            print("Parsed items:")
            for item in items:
                print(f"  [{item['type']}] {item['content'][:50]}")
        else:
            print("Usage:")
            print("  python3 heartbeat.py heartbeat  # Send daily check-in")
            print("  python3 heartbeat.py monitor    # Run capture monitor")
            print("  python3 heartbeat.py test       # Test capture parsing")
    else:
        # Default: send heartbeat
        send_heartbeat()

#!/usr/bin/env python3
"""
Morning Briefing - Daily Slack DM with your context.

Sends you:
- Open action items from meetings
- Recent decisions to remember
- Today's relevant context
- Open blockers

Run manually: python3 morning_briefing.py
Schedule: Add to cron or launchd for 8am daily
"""

import os
from datetime import datetime, timedelta
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from shared_memory import load_memory, load_entities

# Google integrations (optional - gracefully degrade if not configured)
try:
    from google_calendar import get_todays_events
    GCAL_AVAILABLE = True
except (ImportError, Exception):
    GCAL_AVAILABLE = False
    def get_todays_events():
        return []

try:
    from google_tasks import get_all_open_tasks
    GTASKS_AVAILABLE = True
except (ImportError, Exception):
    GTASKS_AVAILABLE = False
    def get_all_open_tasks():
        return []

try:
    from google_sheets import get_my_projects, get_my_gtm_items
    GSHEETS_AVAILABLE = True
except (ImportError, Exception):
    GSHEETS_AVAILABLE = False
    def get_my_projects(name='lucas'):
        return []
    def get_my_gtm_items():
        return []

try:
    from wellness import analyze_load, get_briefing_nudge
    WELLNESS_AVAILABLE = True
except (ImportError, Exception):
    WELLNESS_AVAILABLE = False

try:
    from team_wellness import get_team_status, format_for_briefing as format_team_status
    TEAM_WELLNESS_AVAILABLE = True
except (ImportError, Exception):
    TEAM_WELLNESS_AVAILABLE = False

# Config
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN', '***REDACTED***')
BRIEFING_CHANNEL = "C0AFPAQ0KMF"  # #lucas-briefing
MY_SLACK_EMAIL = "lucas@visitingmedia.com"  # Used to find your user ID
MY_SLACK_USER_ID = "U9NLNTPDK"  # Lucas


def get_my_user_id(client):
    """Look up Slack user ID by email."""
    try:
        result = client.users_lookupByEmail(email=MY_SLACK_EMAIL)
        return result['user']['id']
    except SlackApiError as e:
        print(f"Error looking up user: {e}")
        return None


def build_briefing():
    """Build the morning briefing content."""
    mem = load_memory()

    # Get inbox items
    inbox = mem.get('inbox', [])
    open_actions = [i for i in inbox if i.get('status') == 'open' and i.get('type') == 'action']
    open_deadlines = [i for i in inbox if i.get('status') == 'open' and i.get('type') == 'deadline']

    # Get recent meetings (last 3 days)
    meetings = mem.get('meetings', [])[-10:]

    # Get recent decisions
    recent_decisions = []
    for m in meetings:
        signals = m.get('signals', {})
        for decision in signals.get('decisions', []):
            recent_decisions.append({
                'decision': decision,
                'from': m.get('title', 'Unknown meeting'),
                'date': m.get('date', ''),
            })

    # Get blockers
    blockers = []
    for m in meetings:
        signals = m.get('signals', {})
        for blocker in signals.get('blockers', []):
            blockers.append({
                'blocker': blocker,
                'from': m.get('title', 'Unknown meeting'),
            })

    # Get recent observations from Slack
    observations = mem.get('observations', [])[-10:]

    # Build message blocks
    blocks = []

    # Header - Lucas voice: direct, human
    today = datetime.now().strftime("%A")

    # Craft greeting based on what's on the plate
    if len(open_actions) == 0:
        greeting = f"Hey Lucas—light {today}. Nothing urgent on your plate."
    elif len(open_actions) == 1:
        greeting = f"Hey Lucas—one thing needs your attention today."
    elif len(open_actions) <= 3:
        greeting = f"Hey Lucas—{len(open_actions)} things on your plate today."
    else:
        greeting = f"Hey Lucas—busy day ahead. {len(open_actions)} items need attention."

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"*{greeting}*"}
    })

    # Today's Calendar (if Google Calendar connected)
    try:
        cal_events = get_todays_events()
        if cal_events:
            cal_text = "*Today's calendar:*\n"
            for event in cal_events[:5]:
                cal_text += f"• {event['time']}: {event['title'][:50]}\n"
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": cal_text}})
    except Exception:
        pass  # Gracefully skip if calendar not configured

    # Action Items - direct, no fluff
    if open_actions:
        action_text = ""
        for item in open_actions[:5]:
            content = item['content'][:100] + '...' if len(item['content']) > 100 else item['content']
            action_text += f"• {content}\n"
        if len(open_actions) > 5:
            action_text += f"_...plus {len(open_actions) - 5} more_\n"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": action_text}})

    # Deadlines - only show if there are any
    if open_deadlines:
        deadline_text = "*Deadlines coming up:*\n"
        for item in open_deadlines[:3]:
            content = str(item['content'])[:60] + '...' if len(str(item['content'])) > 60 else str(item['content'])
            deadline_text += f"• {content}\n"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": deadline_text}})

    # Google Tasks (if connected)
    try:
        tasks = get_all_open_tasks()
        if tasks:
            blocks.append({"type": "divider"})
            # Show tasks with due dates first, then others
            due_tasks = [t for t in tasks if t.get('due')]
            other_tasks = [t for t in tasks if not t.get('due')]
            show_tasks = (due_tasks + other_tasks)[:5]

            tasks_text = "*Google Tasks:*\n"
            for t in show_tasks:
                due = f" _(due {t['due']})_" if t.get('due') else ""
                tasks_text += f"• {t['title'][:60]}{due}\n"
            if len(tasks) > 5:
                tasks_text += f"_...plus {len(tasks) - 5} more_\n"
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": tasks_text}})
    except Exception:
        pass

    # GTM Items (canonical deadlines from tracking sheet)
    try:
        gtm_items = get_my_gtm_items()
        if gtm_items:
            gtm_text = "*GTM deadlines:*\n"
            for item in gtm_items[:4]:
                status_icon = "🔄" if 'wip' in item['status'].lower() else "⏳"
                due = f" _(due {item['due']})_" if item.get('due') else ""
                gtm_text += f"• {status_icon} {item['task'][:45]}{due}\n"
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": gtm_text}})
    except Exception:
        pass

    # Team wellness (direct reports)
    if TEAM_WELLNESS_AVAILABLE:
        try:
            team_status = get_team_status()
            if team_status:
                team_text = format_team_status(team_status)
                blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": team_text}})
        except Exception:
            pass

    # Blockers - only show if there are any
    if blockers:
        blocks.append({"type": "divider"})
        blocker_text = "*Heads up—blockers:*\n"
        for b in blockers[:3]:
            blk = str(b['blocker'])[:80] + '...' if len(str(b['blocker'])) > 80 else str(b['blocker'])
            blocker_text += f"• {blk}\n"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": blocker_text}})

    # Curated context (messages you pasted to #lucas-briefing)
    curated = [obs for obs in observations if obs.get('curated')]
    if curated:
        blocks.append({"type": "divider"})
        curated_text = "*Notes you captured:*\n"
        for item in curated[-3:]:  # Last 3 curated items
            content = item.get('content', '')[:150]
            if len(item.get('content', '')) > 150:
                content += '...'
            curated_text += f"• {content}\n"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": curated_text}})

    # Slack Activity Summary
    if observations:
        themes = {}
        for obs in observations:
            for theme in obs.get('themes', []):
                themes[theme] = themes.get(theme, 0) + 1

        if themes:
            top_themes = sorted(themes.items(), key=lambda x: x[1], reverse=True)[:3]
            theme_text = "*📡 Slack Activity:* " + ", ".join([f"{t[0]} ({t[1]})" for t in top_themes])
            blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": theme_text}]})

    # Wellness nudge (only shows when warranted)
    if WELLNESS_AVAILABLE:
        try:
            cal_events = get_todays_events() if GCAL_AVAILABLE else []
            tasks = get_all_open_tasks() if GTASKS_AVAILABLE else []
            indicators = analyze_load(cal_events, inbox, tasks)
            nudge = get_briefing_nudge(indicators)
            if nudge:
                blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"_{nudge}_"}]})
        except Exception:
            pass

    # Interactive prompt
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "📝 *Lucas, what's on your paper notepad today?*\nReply with any items and I can add them to your Google Tasks."
        }
    })

    # Footer
    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "_Commands: 'done [item]' to complete • 'add [task]' to add • 'summary' for more detail_"}]
    })

    return blocks


def send_briefing(test_mode=False, to_channel=True):
    """Send the morning briefing to #lucas-briefing channel."""
    if not SLACK_BOT_TOKEN:
        print("Error: SLACK_BOT_TOKEN not set")
        return False

    client = WebClient(token=SLACK_BOT_TOKEN)

    # Build the briefing
    blocks = build_briefing()

    if test_mode:
        print("\n=== BRIEFING PREVIEW ===")
        import json
        print(json.dumps(blocks, indent=2))
        print("========================\n")
        return True

    # Send to channel or DM
    try:
        if to_channel:
            channel_id = BRIEFING_CHANNEL
            print(f"Sending briefing to #lucas-briefing...")
        else:
            # Send as DM
            dm = client.conversations_open(users=[MY_SLACK_USER_ID])
            channel_id = dm['channel']['id']
            print(f"Sending briefing as DM...")

        # Send message
        result = client.chat_postMessage(
            channel=channel_id,
            blocks=blocks,
            text="Morning Briefing"  # Fallback text
        )

        print(f"✅ Briefing sent!")
        return True

    except SlackApiError as e:
        print(f"Error sending message: {e}")
        return False


def preview_briefing():
    """Preview the briefing without sending."""
    blocks = build_briefing()

    print("\n" + "=" * 50)
    print("MORNING BRIEFING PREVIEW")
    print("=" * 50)

    for block in blocks:
        if block.get('type') == 'header':
            print(f"\n{block['text']['text']}")
            print("-" * 40)
        elif block.get('type') == 'section':
            text = block.get('text', {}).get('text', '')
            # Simple markdown cleanup for terminal
            text = text.replace('*', '').replace('_', '')
            print(text)
        elif block.get('type') == 'context':
            for elem in block.get('elements', []):
                text = elem.get('text', '').replace('*', '').replace('_', '')
                print(f"  {text}")
        elif block.get('type') == 'divider':
            print("-" * 40)

    print("=" * 50 + "\n")


if __name__ == '__main__':
    import sys

    if '--preview' in sys.argv:
        preview_briefing()
    elif '--send' in sys.argv:
        send_briefing()
    else:
        print("Morning Briefing")
        print()
        print("Usage:")
        print("  python3 morning_briefing.py --preview  # Preview without sending")
        print("  python3 morning_briefing.py --send     # Send to Slack DM")
        print()
        print("Set SLACK_BOT_TOKEN environment variable first.")

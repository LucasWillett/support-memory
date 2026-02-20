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
    from google_tasks import get_all_open_tasks, categorize_tasks, complete_task_by_title, get_all_tasks_by_category
    GTASKS_AVAILABLE = True
except (ImportError, Exception):
    GTASKS_AVAILABLE = False
    def get_all_open_tasks():
        return []
    def categorize_tasks(tasks):
        return {'actionable': tasks, 'learning': [], 'reference': []}
    def complete_task_by_title(text):
        return None
    def get_all_tasks_by_category():
        return {}

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
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
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

    # Fetch Google Tasks early — source of truth for "on your plate"
    top_tasks = []
    tasks_by_category = {}
    try:
        tasks_by_category = get_all_tasks_by_category()
        for tasks in tasks_by_category.values():
            top_tasks.extend(tasks)
        top_tasks = top_tasks[:5]
    except Exception:
        try:
            top_tasks = get_all_open_tasks()[:5]
        except Exception:
            top_tasks = []

    # Build message blocks
    blocks = []

    # Header — greeting based on Google Tasks count
    today = datetime.now().strftime("%A")
    task_count = len(top_tasks)
    if task_count == 0:
        greeting = f"Hey Lucas—light {today}. Nothing in your task list."
    elif task_count == 1:
        greeting = f"Hey Lucas—one thing on your plate today."
    elif task_count <= 3:
        greeting = f"Hey Lucas—{task_count} things on your plate today."
    else:
        greeting = f"Hey Lucas—busy day ahead. {task_count}+ tasks in your list."

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"*{greeting}*"}
    })

    # Top tasks — shown right after greeting
    if top_tasks:
        task_text = ""
        for t in top_tasks:
            title = t['title'][:80]
            if 'http' in title:
                title = title.split('http')[0].strip() + '...'
            task_text += f"• {title}\n"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": task_text}})

    # Today's Calendar
    try:
        cal_events = get_todays_events()
        if cal_events:
            cal_text = "*Today's calendar:*\n"
            for event in cal_events[:5]:
                cal_text += f"• {event['time']}: {event['title'][:50]}\n"
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": cal_text}})
    except Exception:
        pass

    # Full Google Tasks by category (below the fold)
    if tasks_by_category:
        blocks.append({"type": "divider"})
        total_tasks = sum(len(t) for t in tasks_by_category.values())
        tasks_text = f"*📋 Google Tasks* ({total_tasks} open)\n\n"
        for cat_name, tasks in list(tasks_by_category.items())[:5]:
            if cat_name == 'Uncategorized':
                continue
            cat_count = len(tasks)
            tasks_text += f"*{cat_name}* ({cat_count})\n"
            for t in tasks[:2]:
                title = t['title'][:45]
                if 'http' in title:
                    title = title.split('http')[0].strip() + '...'
                tasks_text += f"  • {title}\n"
            if cat_count > 2:
                tasks_text += f"  _+{cat_count - 2} more_\n"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": tasks_text}})

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

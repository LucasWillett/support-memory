#!/usr/bin/env python3
"""
Slack Listener - Reads from channels, writes to shared memory.
Does NOT post anything to Slack.

Monitors:
- #gtm-weekly
- #saleshub-eng
- #product-studios
- #channel-distribution
- (add more as needed)

Extracts:
- Customer mentions
- Project updates
- Themes and topics
- Action items
"""
import os
import re
import time
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from shared_memory import load_memory, save_memory, load_entities, save_entities
from curated_parser import parse_curated_message, create_inbox_item
from google_calendar import check_meeting_scheduled, create_event
from datetime import timedelta
import subprocess

# Slack config
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')

# Channels to monitor
MONITOR_CHANNELS = {
    "C066S5LHUUE": "support-desk",
    "C03DFHCLTPX": "channel-distribution",
    "C06K6MRSBJ5": "eng-alarms",
    "C05506BHAPN": "product-incident-management",
    "C021RP67MTP": "product",
    "CG8D7DW9J": "product-reportadefect",
    "C01MX8YKDLM": "product-studio",
    "C09B1UCL3LG": "beta-launch",
    "C08QP5KUBGT": "migration-support",
    "C08RF5K90Q2": "nps_results",
    "C031R5ZPU6M": "saleshub",
    "C6STGEZ0R": "general",
    "C7HQ6V62C": "customer-experience",
    "C04A0Q69U0N": "pendo",
    # Lucas's curated context channel - pasted DMs and important messages go here
    "C0AFPAQ0KMF": "lucas-briefing",
    # Help Center article ideas - triggers article pipeline processor
    "C0AFK5PHE5Q": "help-center-ideas",
    # Private channels (need groups:read scope to access):
    # "gtm-weekly", "cx-external", "cx-internal", "it-jira-notifications"
}

# Special channel that triggers article pipeline
ARTICLE_IDEAS_CHANNEL = "C0AFK5PHE5Q"

# Special channel for curated content - gets fuller context capture
CURATED_CHANNEL = "C0AFPAQ0KMF"

# How far back to look (in seconds)
LOOKBACK_SECONDS = 3600  # 1 hour

# Known customer names to watch for
CUSTOMER_KEYWORDS = [
    # Add your key accounts here
    "acme", "bigco",
]

# Project keywords to track
PROJECT_KEYWORDS = [
    "truetour", "embed", "integration", "launch", "release",
    "beta", "pilot", "migration", "rollout",
]

# Theme patterns
THEME_PATTERNS = {
    "customer_issue": r"(issue|problem|bug|broken|not working|error)",
    "feature_request": r"(would be nice|feature request|can we add|should have)",
    "positive_feedback": r"(love|great|awesome|excited|happy)",
    "deadline": r"(deadline|due|by end of|eod|eow|asap)",
    "blocker": r"(blocked|waiting on|dependency|need.*before)",
}


class SlackListener:
    def __init__(self, token):
        self.client = WebClient(token=token)
        self.processed_messages = set()

    def get_channel_history(self, channel_id, limit=50):
        """Get recent messages from a channel."""
        try:
            result = self.client.conversations_history(
                channel=channel_id,
                limit=limit
            )
            return result.get('messages', [])
        except SlackApiError as e:
            print(f"Error reading {channel_id}: {e}")
            return []

    def extract_insights(self, text, channel_name):
        """Extract insights from a message."""
        text_lower = text.lower()
        insights = {
            "customers_mentioned": [],
            "projects_mentioned": [],
            "themes": [],
            "channel": channel_name,
            "timestamp": datetime.now().isoformat(),
        }

        # Find customer mentions
        for customer in CUSTOMER_KEYWORDS:
            if customer in text_lower:
                insights["customers_mentioned"].append(customer)

        # Find project mentions
        for project in PROJECT_KEYWORDS:
            if project in text_lower:
                insights["projects_mentioned"].append(project)

        # Detect themes
        for theme, pattern in THEME_PATTERNS.items():
            if re.search(pattern, text_lower):
                insights["themes"].append(theme)

        return insights

    def update_memory(self, insights, raw_text, is_curated=False):
        """Update shared memory with insights."""
        # For curated content, always store it (Lucas decided it's important)
        if not is_curated and not any([insights["customers_mentioned"],
                    insights["projects_mentioned"],
                    insights["themes"]]):
            return  # Nothing interesting

        mem = load_memory()

        # Log as an observation
        if "observations" not in mem:
            mem["observations"] = []

        observation = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": datetime.now().strftime("%H:%M"),
            "channel": insights["channel"],
            "customers": insights["customers_mentioned"],
            "projects": insights["projects_mentioned"],
            "themes": insights["themes"],
        }

        # Curated content gets full text (up to 1000 chars) since Lucas chose to share it
        if is_curated:
            observation["curated"] = True
            observation["content"] = raw_text[:1000] + "..." if len(raw_text) > 1000 else raw_text

            # Parse curated content for meetings, dates, people
            parsed = parse_curated_message(raw_text)
            if parsed['has_meeting']:
                observation["parsed"] = {
                    "meeting_date": parsed['meeting_date'],
                    "people": parsed['people'],
                    "topics": parsed['topics'][:3],
                    "is_scheduled": parsed['is_scheduled'],
                }

                # Add to inbox if it looks like a meeting
                inbox_item = create_inbox_item(parsed, source='curated')
                if inbox_item:
                    if "inbox" not in mem:
                        mem["inbox"] = []
                    mem["inbox"].append(inbox_item)
                    mem["inbox"] = mem["inbox"][-100:]  # Keep manageable
                    print(f"  → Meeting detected: {', '.join(parsed['people'])} on {parsed['meeting_date']}")

                    # Auto-create calendar event if marked as scheduled and has date
                    if parsed['is_scheduled'] and parsed['meeting_date'] and parsed['people']:
                        # Check if meeting already exists
                        person = parsed['people'][0]
                        existing = check_meeting_scheduled(person, days_ahead=30)

                        if not existing or parsed['meeting_date'] not in existing.get('date', ''):
                            # Create calendar event
                            try:
                                from datetime import datetime as dt
                                meeting_date = dt.strptime(parsed['meeting_date'], '%Y-%m-%d')
                                # Default to 10am if no time specified
                                meeting_time = meeting_date.replace(hour=10, minute=0)
                                duration = parsed['duration_minutes'] or 30

                                title = f"Meeting: {', '.join(parsed['people'][:2])}"
                                if parsed['topics']:
                                    title = f"{parsed['topics'][0][:40]}"

                                event = create_event(
                                    title=title,
                                    start_time=meeting_time,
                                    duration_minutes=duration,
                                    description=f"Auto-created from Slack.\nPeople: {', '.join(parsed['people'])}\nTopics: {'; '.join(parsed['topics'][:3])}"
                                )
                                if event:
                                    print(f"  → Calendar event created: {event['title']} on {event['date']}")
                                    inbox_item['calendar_created'] = True
                            except Exception as e:
                                print(f"  → Could not create calendar event: {e}")
        else:
            observation["snippet"] = raw_text[:200] + "..." if len(raw_text) > 200 else raw_text

        mem["observations"].append(observation)

        # Keep only last 100 observations
        mem["observations"] = mem["observations"][-100:]

        save_memory(mem)

        if not is_curated:
            print(f"  → Logged: {insights['themes']} | customers: {insights['customers_mentioned']}")

    def scan_channel(self, channel_id, channel_name):
        """Scan a channel for insights."""
        messages = self.get_channel_history(channel_id)
        new_insights = 0
        is_curated = (channel_id == CURATED_CHANNEL)

        for msg in messages:
            msg_ts = msg.get('ts')
            text = msg.get('text', '')

            # Skip if already processed
            if msg_ts in self.processed_messages:
                continue

            # Skip bot messages UNLESS it's the curated channel (briefings are from bot)
            if msg.get('bot_id') and not is_curated:
                continue

            # For curated channel, skip the morning briefing bot messages (they're output, not input)
            # Only capture messages Lucas posts himself
            if is_curated and msg.get('bot_id'):
                continue

            self.processed_messages.add(msg_ts)

            # Extract and store insights
            insights = self.extract_insights(text, channel_name)

            # Curated content always gets stored (Lucas chose to share it)
            if is_curated and text.strip():
                self.update_memory(insights, text, is_curated=True)
                new_insights += 1
            elif any([insights["customers_mentioned"],
                    insights["projects_mentioned"],
                    insights["themes"]]):
                self.update_memory(insights, text)
                new_insights += 1

        return new_insights

    def trigger_article_pipeline(self):
        """Trigger the help center article pipeline processor."""
        try:
            print("  → Triggering article pipeline processor...")
            result = subprocess.run(
                ['python3', '/Users/lucaswillett/projects/support-memory/help-center/process_article_ideas.py'],
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode == 0:
                # Print last line of output (summary)
                lines = result.stdout.strip().split('\n')
                if lines:
                    print(f"  → Pipeline: {lines[-1]}")
            else:
                print(f"  → Pipeline error: {result.stderr[:100]}")
        except Exception as e:
            print(f"  → Could not run pipeline: {e}")

    def check_article_ideas_channel(self):
        """Check for any new messages in #help-center-ideas (separate from insights)."""
        try:
            messages = self.get_channel_history(ARTICLE_IDEAS_CHANNEL, limit=20)
            new_messages = 0
            for msg in messages:
                msg_ts = msg.get('ts')
                if msg_ts in self.processed_messages:
                    continue
                # Skip bot messages and system messages
                if msg.get('bot_id'):
                    continue
                if msg.get('subtype') in ['channel_join', 'channel_leave']:
                    continue
                text = msg.get('text', '')
                if 'has joined the channel' in text:
                    continue
                # Skip threaded replies
                if msg.get('thread_ts') and msg.get('thread_ts') != msg.get('ts'):
                    continue
                if len(text) >= 20:  # Minimum length for submission
                    new_messages += 1
                    self.processed_messages.add(msg_ts)
            return new_messages
        except Exception as e:
            print(f"  Error checking article ideas: {e}")
            return 0

    def run_once(self):
        """Single scan of all channels."""
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Scanning Slack channels...")
        total = 0

        for channel_id, channel_name in MONITOR_CHANNELS.items():
            count = self.scan_channel(channel_id, channel_name)
            if count:
                print(f"  #{channel_name}: {count} new insights")
            total += count

        # Always check article ideas channel separately (doesn't need to match insight patterns)
        article_count = self.check_article_ideas_channel()
        if article_count > 0:
            print(f"  #help-center-ideas: {article_count} new submission(s)")
            self.trigger_article_pipeline()

        if total == 0 and article_count == 0:
            print("  No new insights found")
        return total

    def run_continuous(self, interval=60):
        """Continuous monitoring loop."""
        print("=" * 50)
        print("SLACK LISTENER")
        print("=" * 50)
        print(f"Monitoring {len(MONITOR_CHANNELS)} channels")
        print(f"Poll interval: {interval}s")
        print("Reading only - will NOT post to Slack")
        print("-" * 50)

        while True:
            try:
                self.run_once()
                time.sleep(interval)
            except KeyboardInterrupt:
                print("\nListener stopped.")
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(interval)


def list_channels():
    """Helper to list available channels."""
    if not SLACK_BOT_TOKEN:
        print("Set SLACK_BOT_TOKEN environment variable")
        return

    client = WebClient(token=SLACK_BOT_TOKEN)
    try:
        result = client.conversations_list(types="public_channel", limit=100)
        print("\nAvailable channels:")
        print("-" * 40)
        for ch in sorted(result['channels'], key=lambda x: x['name']):
            print(f"  {ch['id']}: #{ch['name']}")
    except SlackApiError as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    import sys

    if "--list-channels" in sys.argv:
        list_channels()
    elif not SLACK_BOT_TOKEN:
        print("Set SLACK_BOT_TOKEN environment variable")
        print("\nTo list channels: python3 slack_listener.py --list-channels")
    elif not MONITOR_CHANNELS:
        print("No channels configured. Run with --list-channels to get IDs")
        print("Then add them to MONITOR_CHANNELS dict")
    else:
        listener = SlackListener(SLACK_BOT_TOKEN)
        listener.run_continuous()

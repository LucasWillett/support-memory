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
    # Private channels (need groups:read scope to access):
    # "gtm-weekly", "cx-external", "cx-internal", "it-jira-notifications"
}

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

    def update_memory(self, insights, raw_text):
        """Update shared memory with insights."""
        if not any([insights["customers_mentioned"],
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
            "snippet": raw_text[:200] + "..." if len(raw_text) > 200 else raw_text,
        }

        mem["observations"].append(observation)

        # Keep only last 100 observations
        mem["observations"] = mem["observations"][-100:]

        save_memory(mem)
        print(f"  → Logged: {insights['themes']} | customers: {insights['customers_mentioned']}")

    def scan_channel(self, channel_id, channel_name):
        """Scan a channel for insights."""
        messages = self.get_channel_history(channel_id)
        new_insights = 0

        for msg in messages:
            msg_ts = msg.get('ts')
            text = msg.get('text', '')

            # Skip if already processed or bot message
            if msg_ts in self.processed_messages:
                continue
            if msg.get('bot_id'):
                continue

            self.processed_messages.add(msg_ts)

            # Extract and store insights
            insights = self.extract_insights(text, channel_name)
            if any([insights["customers_mentioned"],
                    insights["projects_mentioned"],
                    insights["themes"]]):
                self.update_memory(insights, text)
                new_insights += 1

        return new_insights

    def run_once(self):
        """Single scan of all channels."""
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Scanning Slack channels...")
        total = 0

        for channel_id, channel_name in MONITOR_CHANNELS.items():
            count = self.scan_channel(channel_id, channel_name)
            if count:
                print(f"  #{channel_name}: {count} new insights")
            total += count

        if total == 0:
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

#!/usr/bin/env python3
"""
Redirect Checker Slack Bot - For #support-internal

Monitors channel for redirect check requests.
Usage: Post "check redirects: https://property-url.com"
       or "redirect check https://property-url.com"

Results posted back to the channel.
"""

import os
import re
import sys
import time
import json
import subprocess
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Config
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')

# Channels to monitor
CHANNELS = {
    'C05U74HDVLH': 'support-internal',
    'C0AGULNT9EU': 'lucas-bot-testing',
}

# Lucas's Slack user ID for tagging on zero-result crawls
LUCAS_USER_ID = "U9NLNTPDK"

# Path to redirect checker
REDIRECT_CHECKER_PATH = "/Users/lucaswillett/projects/redirect-checker/redirect_checker.py"

# Google Sheets result sheet
RESULTS_SHEET_ID = "18UAf2hhgdS0-tjADyEkRXCPqksGDYPYA67Hd9MYJX1I"
RESULTS_SHEET_URL = f"https://docs.google.com/spreadsheets/d/{RESULTS_SHEET_ID}/edit"

# Patterns to trigger redirect check
TRIGGER_PATTERNS = [
    r'check\s+redirects?[:\s]+(\S+)',
    r'check\s+redirects?\s+(?:on|for|at)\s+(\S+)',
    r'redirect\s+check[:\s]+(\S+)',
    r'redirect\s+check\s+(?:on|for|at)\s+(\S+)',
    r'scan\s+redirects?[:\s]+(\S+)',
    r'scan\s+redirects?\s+(?:on|for|at)\s+(\S+)',
    r'run\s+redirect\s+(?:check|checker|scan)[:\s]+(\S+)',
    r'run\s+redirect\s+(?:check|checker|scan)\s+(?:on|for|at)\s+(\S+)',
]


class RedirectSlackBot:
    def __init__(self, token, channels):
        self.client = WebClient(token=token)
        self.channels = channels  # dict of {channel_id: channel_name}
        self.processed_messages = set()
        self.bot_user_id = None

    def get_bot_user_id(self):
        """Get our bot's user ID to avoid responding to ourselves."""
        if not self.bot_user_id:
            try:
                result = self.client.auth_test()
                self.bot_user_id = result['user_id']
            except SlackApiError as e:
                print(f"Error getting bot user ID: {e}")
        return self.bot_user_id

    def check_for_requests(self):
        """Check all channels for new redirect check requests."""
        bot_id = self.get_bot_user_id()

        for channel_id, channel_name in self.channels.items():
            try:
                result = self.client.conversations_history(
                    channel=channel_id,
                    limit=20
                )

                messages = result.get('messages', [])

                for msg in messages:
                    msg_ts = msg.get('ts')
                    text = msg.get('text', '')
                    user = msg.get('user', '')

                    # Skip if already processed, from bot, or is a bot message
                    if msg_ts in self.processed_messages:
                        continue
                    if user == bot_id or msg.get('bot_id'):
                        continue

                    self.processed_messages.add(msg_ts)

                    # Check for trigger patterns
                    url = self.extract_url(text)
                    if url:
                        print(f"[#{channel_name}] Redirect check requested: {url}")
                        self.handle_redirect_check(url, msg_ts, channel_id)

            except SlackApiError as e:
                print(f"Error reading #{channel_name}: {e}")

    def extract_url(self, text):
        """Extract URL from a redirect check request."""
        # First, extract any URLs from Slack's formatting <url|text>
        slack_urls = re.findall(r'<(https?://[^|>]+)(?:\|[^>]*)?>',text)

        text_clean = text.lower()

        for pattern in TRIGGER_PATTERNS:
            match = re.search(pattern, text_clean)
            if match:
                # If we found Slack-formatted URLs, use the first one
                if slack_urls:
                    return slack_urls[0]

                # Otherwise try to extract from the match
                url = match.group(1)
                url = url.strip('<>|')
                if url.startswith('http'):
                    return url

        # Fallback: check if message contains redirect keywords and a URL
        redirect_keywords = ['redirect', 'check redirect', 'scan redirect']
        if any(kw in text_clean for kw in redirect_keywords):
            if slack_urls:
                return slack_urls[0]
            # Try to find any http URL in the text
            url_match = re.search(r'(https?://\S+)', text)
            if url_match:
                return url_match.group(1).rstrip('>')

        return None

    def handle_redirect_check(self, url, thread_ts, channel_id):
        """Run redirect checker and post results."""
        # Acknowledge the request
        self.post_message(f"🔍 Checking redirects for: {url}\nThis may take a minute...", thread_ts, channel_id)

        try:
            # Run the redirect checker
            result = self.run_redirect_checker(url)

            if result['success']:
                # Format results
                summary = result['summary']
                property_name = result.get('property_name', 'Property')

                if summary['total'] == 0:
                    # Zero results - tag Lucas to verify the crawl
                    msg = f"⚠️ *Redirect Check: No tours found*\n\n"
                    msg += f"*URL:* {url}\n"
                    msg += f"Crawled the site but found 0 visitingmedia tour links.\n\n"
                    msg += f"<@{LUCAS_USER_ID}> can you verify the crawler ran correctly? "
                    msg += f"The site may be blocking the crawl or the tours may be loaded via JS that the crawler didn't pick up."
                else:
                    msg = f"✅ *Redirect Check Complete*\n\n"
                    msg += f"*URL:* {url}\n"
                    msg += f"*Total Tours Found:* {summary['total']}\n"
                    msg += f"*Good:* {summary['good']} | *Bad:* {summary['bad']} | *Errors:* {summary['errors']}\n"

                    if summary['bad'] > 0:
                        msg += f"\n⚠️ *{summary['bad']} bad redirects found*\n"
                        # List first few bad ones
                        for item in result.get('bad_items', [])[:5]:
                            msg += f"• {item}\n"
                        if summary['bad'] > 5:
                            msg += f"_...and {summary['bad'] - 5} more_\n"

                    msg += f"\n📊 *Results:* <{RESULTS_SHEET_URL}|View in Google Sheets>\n"
                    msg += f"\n⚠️ *Important:* This sheet gets overwritten with each new request.\n"
                    msg += f"→ Make a copy: *File > Make a copy*\n"
                    msg += f"→ Rename it: *{property_name} - Redirect Results*\n"
                    msg += f"→ Share with edit access if needed"

            else:
                msg = f"❌ *Error running redirect check*\n{result.get('error', 'Unknown error')}"

            self.post_message(msg, thread_ts, channel_id)

        except Exception as e:
            self.post_message(f"❌ Error: {str(e)}", thread_ts, channel_id)

    def run_redirect_checker(self, url):
        """Run the redirect checker script."""
        try:
            # Extract property name from URL
            name = url.split('/')[-1].replace('.html', '').replace('-', ' ').title()
            if not name:
                name = "Property"

            # Run the checker with piped inputs
            inputs = f"{url}\n{name}\n30\n"

            proc = subprocess.run(
                ['python3', REDIRECT_CHECKER_PATH],
                input=inputs,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=os.path.dirname(REDIRECT_CHECKER_PATH)
            )

            output = proc.stdout + proc.stderr

            # Parse results from output
            total_match = re.search(r'Total: (\d+)', output)
            good_match = re.search(r'GOOD: (\d+)', output)
            bad_match = re.search(r'BAD: (\d+)', output)
            errors_match = re.search(r'ERRORS: (\d+)', output)

            # Find bad redirect pages
            bad_items = []
            for line in output.split('\n'):
                if 'BAD REDIRECT' in line:
                    # Get the previous line which has the page URL
                    pass
                if 'Found visitingmedia' in line:
                    # The URL is on the line before
                    pass

            return {
                'success': True,
                'summary': {
                    'total': int(total_match.group(1)) if total_match else 0,
                    'good': int(good_match.group(1)) if good_match else 0,
                    'bad': int(bad_match.group(1)) if bad_match else 0,
                    'errors': int(errors_match.group(1)) if errors_match else 0,
                },
                'property_name': name,
                'output': output,
            }

        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Timeout - check took too long'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def post_message(self, text, thread_ts=None, channel_id=None):
        """Post a message to a channel."""
        try:
            self.client.chat_postMessage(
                channel=channel_id,
                text=text,
                thread_ts=thread_ts
            )
        except SlackApiError as e:
            print(f"Error posting message: {e}")

    def run(self, poll_interval=5):
        """Main loop - poll for new messages."""
        print("=" * 50)
        print("REDIRECT CHECKER SLACK BOT")
        print("=" * 50)
        print(f"Channels: {', '.join([f'#{name}' for name in self.channels.values()])}")
        print(f"Poll interval: {poll_interval}s")
        print("Watching for: 'check redirects: URL'")
        print("-" * 50)

        # Mark recent messages as processed to avoid re-checking old requests
        total_skipped = 0
        for channel_id, channel_name in self.channels.items():
            try:
                result = self.client.conversations_history(channel=channel_id, limit=50)
                for msg in result.get('messages', []):
                    self.processed_messages.add(msg.get('ts'))
                    total_skipped += 1
            except Exception as e:
                print(f"Warning: Could not read #{channel_name}: {e}")

        print(f"Skipped {total_skipped} existing messages")
        print("Listening for redirect check requests...")

        while True:
            try:
                self.check_for_requests()
                time.sleep(poll_interval)
            except KeyboardInterrupt:
                print("\nBot stopped.")
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(poll_interval)


if __name__ == '__main__':
    if not SLACK_BOT_TOKEN:
        print("Set SLACK_BOT_TOKEN environment variable")
        print("\nUsage:")
        print("  export SLACK_BOT_TOKEN='xoxb-...'")
        print("  python3 redirect_slack_bot.py")
        sys.exit(1)

    bot = RedirectSlackBot(SLACK_BOT_TOKEN, CHANNELS)
    bot.run()

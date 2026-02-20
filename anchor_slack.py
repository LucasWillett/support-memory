#!/usr/bin/env python3
"""
Anchor Slack Integration
Allows Claude Code (Anchor) to send Slack messages directly.

Usage:
    python3 anchor_slack.py send "#channel" "message"
    python3 anchor_slack.py dm "@user" "message"
    python3 anchor_slack.py dm "U9NLNTPDK" "message"  # by user ID
"""

import os
import sys
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Use same token as other bots
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')

# Known channels
CHANNELS = {
    'support-internal': 'C05U74HDVLH',
    'redirect-requests': 'C040MMBB7NG',
    'channel-distribution': 'C03DFHCLTPX',
}

# Known users (add more as needed)
USERS = {
    'lucas': 'U9NLNTPDK',
}

client = WebClient(token=SLACK_BOT_TOKEN)


def send_message(channel, text, thread_ts=None):
    """Send a message to a channel or DM."""
    try:
        # Resolve channel name to ID
        if channel.startswith('#'):
            channel_name = channel[1:].lower()
            channel_id = CHANNELS.get(channel_name, channel_name)
        elif channel.startswith('@'):
            # DM to user
            user_name = channel[1:].lower()
            user_id = USERS.get(user_name, channel[1:])
            # Open DM channel
            result = client.conversations_open(users=[user_id])
            channel_id = result['channel']['id']
        elif channel.startswith('C') or channel.startswith('D'):
            # Already a channel/DM ID
            channel_id = channel
        else:
            # Assume it's a channel name
            channel_id = CHANNELS.get(channel.lower(), channel)

        # Send message
        result = client.chat_postMessage(
            channel=channel_id,
            text=text,
            thread_ts=thread_ts
        )
        print(f"✓ Sent to {channel}: {text[:50]}{'...' if len(text) > 50 else ''}")
        return result

    except SlackApiError as e:
        print(f"✗ Error: {e.response['error']}")
        return None


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command in ('send', 'dm'):
        channel = sys.argv[2]
        message = ' '.join(sys.argv[3:])
        if not message:
            print("Error: Message required")
            sys.exit(1)
        send_message(channel, message)
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()

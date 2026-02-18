#!/usr/bin/env python3
"""
Command Bot - Run automation from Slack (works from phone!)

Monitors #lucas-briefing for commands and executes them.
Commands are prefixed with ! to avoid conflicts with Slack slash commands.

Usage:
  !status          - Show what's running and system health
  !run watcher     - Trigger folder watcher (check for article moves)
  !run pipeline    - Process new article ideas
  !run briefing    - Generate morning briefing (preview, doesn't send)
  !run redirects   - Show redirect checker status
  !tasks           - Show task list
  !help            - Show available commands
"""

import os
import sys
import time
import subprocess
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Config
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN', '***REDACTED***')
COMMAND_CHANNEL = "C0AFPAQ0KMF"  # #lucas-briefing
LUCAS_USER_ID = "U9NLNTPDK"

# Only allow commands from Lucas
ALLOWED_USERS = [LUCAS_USER_ID]

# Base paths
SUPPORT_MEMORY_DIR = "/Users/lucaswillett/projects/support-memory"
HELP_CENTER_DIR = f"{SUPPORT_MEMORY_DIR}/help-center"
PYTHON = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"

# Available commands
COMMANDS = {
    "status": {
        "description": "Show what's running and system health",
        "handler": "cmd_status",
    },
    "run watcher": {
        "description": "Check for article moves in Drive folders",
        "handler": "cmd_run_watcher",
    },
    "run pipeline": {
        "description": "Process new article ideas from Slack",
        "handler": "cmd_run_pipeline",
    },
    "run briefing": {
        "description": "Generate morning briefing (preview)",
        "handler": "cmd_run_briefing",
    },
    "tasks": {
        "description": "Show pipeline task status",
        "handler": "cmd_tasks",
    },
    "help": {
        "description": "Show available commands",
        "handler": "cmd_help",
    },
    "services": {
        "description": "Show launchd service status",
        "handler": "cmd_services",
    },
}

client = WebClient(token=SLACK_BOT_TOKEN)


def post_reply(text, thread_ts):
    """Post a reply in thread."""
    try:
        client.chat_postMessage(
            channel=COMMAND_CHANNEL,
            text=text,
            thread_ts=thread_ts
        )
    except SlackApiError as e:
        print(f"Error posting: {e}")


def run_script(script_path, args=None, timeout=60):
    """Run a Python script and return output."""
    cmd = [PYTHON, script_path]
    if args:
        cmd.extend(args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.dirname(script_path)
        )
        output = result.stdout
        if result.stderr:
            output += f"\n{result.stderr}"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "⚠️ Command timed out"
    except Exception as e:
        return f"❌ Error: {e}"


def cmd_status(thread_ts):
    """Show system status."""
    status = []
    status.append("*System Status*\n")

    # Check launchd services
    services = [
        ("slack-listener", "com.supportmemory.slack-listener"),
        ("morning-briefing", "com.supportmemory.morning-briefing"),
        ("article-pipeline", "com.supportmemory.article-pipeline"),
    ]

    status.append("*Services:*")
    for name, label in services:
        result = subprocess.run(
            ["launchctl", "list", label],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            # Parse PID and exit code
            parts = result.stdout.strip().split('\t')
            pid = parts[0] if parts[0] != '-' else 'stopped'
            status.append(f"  • {name}: {'🟢 running' if pid != 'stopped' else '🔴 stopped'}")
        else:
            status.append(f"  • {name}: ⚪ not loaded")

    # Pipeline status
    status.append("\n*Article Pipeline:*")
    pipeline_output = run_script(f"{HELP_CENTER_DIR}/process_article_ideas.py", ["status"], timeout=15)
    for line in pipeline_output.split('\n'):
        if 'inbox' in line.lower() or 'draft' in line.lower() or 'review' in line.lower():
            status.append(f"  {line.strip()}")

    # Timestamp
    status.append(f"\n_Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_")

    post_reply('\n'.join(status), thread_ts)


def cmd_run_watcher(thread_ts):
    """Run the folder watcher."""
    post_reply("🔍 Running folder watcher...", thread_ts)
    output = run_script(f"{HELP_CENTER_DIR}/folder_watcher.py", timeout=30)
    post_reply(f"```\n{output}\n```", thread_ts)


def cmd_run_pipeline(thread_ts):
    """Run the article pipeline processor."""
    post_reply("📝 Processing article ideas...", thread_ts)
    output = run_script(f"{HELP_CENTER_DIR}/process_article_ideas.py", timeout=60)
    post_reply(f"```\n{output}\n```", thread_ts)


def cmd_run_briefing(thread_ts):
    """Generate morning briefing preview."""
    post_reply("☀️ Generating briefing preview...", thread_ts)
    output = run_script(f"{SUPPORT_MEMORY_DIR}/morning_briefing.py", timeout=30)
    # Truncate if too long
    if len(output) > 2500:
        output = output[:2500] + "\n...(truncated)"
    post_reply(f"```\n{output}\n```", thread_ts)


def cmd_tasks(thread_ts):
    """Show pipeline status from folder watcher."""
    output = run_script(f"{HELP_CENTER_DIR}/folder_watcher.py", ["status"], timeout=15)
    post_reply(f"*Article Pipeline Status:*\n```\n{output}\n```", thread_ts)


def cmd_services(thread_ts):
    """Show detailed launchd service status."""
    status = ["*LaunchD Services:*\n"]

    services = [
        ("Slack Listener", "com.supportmemory.slack-listener"),
        ("Morning Briefing", "com.supportmemory.morning-briefing"),
        ("Article Pipeline", "com.supportmemory.article-pipeline"),
        ("ChurnZero Bot", "com.churnzero.slack-bot"),
        ("Redirect Bot", "com.redirect.slack-bot"),
    ]

    for name, label in services:
        result = subprocess.run(
            ["launchctl", "list", label],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split('\t')
            pid = parts[0] if len(parts) > 0 else '-'
            exit_code = parts[1] if len(parts) > 1 else '-'

            if pid != '-':
                status.append(f"🟢 *{name}*: running (PID {pid})")
            elif exit_code == '0':
                status.append(f"🟡 *{name}*: idle (last exit: success)")
            else:
                status.append(f"🔴 *{name}*: stopped (exit code: {exit_code})")
        else:
            status.append(f"⚪ *{name}*: not loaded")

    post_reply('\n'.join(status), thread_ts)


def cmd_help(thread_ts):
    """Show help."""
    help_text = "*Available Commands:*\n\n"
    for cmd, info in COMMANDS.items():
        help_text += f"`!{cmd}` - {info['description']}\n"
    help_text += "\n_Commands only work for authorized users._"
    post_reply(help_text, thread_ts)


class CommandBot:
    def __init__(self):
        self.processed_messages = set()
        self.bot_user_id = None

    def get_bot_user_id(self):
        if not self.bot_user_id:
            try:
                result = client.auth_test()
                self.bot_user_id = result['user_id']
            except SlackApiError:
                pass
        return self.bot_user_id

    def check_for_commands(self):
        """Check for new commands."""
        bot_id = self.get_bot_user_id()

        try:
            result = client.conversations_history(
                channel=COMMAND_CHANNEL,
                limit=10
            )

            for msg in result.get('messages', []):
                msg_ts = msg.get('ts')
                text = msg.get('text', '').strip()
                user = msg.get('user', '')

                # Skip if already processed, from bot, or not a command
                if msg_ts in self.processed_messages:
                    continue
                if user == bot_id or msg.get('bot_id'):
                    continue
                if not text.startswith('!'):
                    continue

                self.processed_messages.add(msg_ts)

                # Check authorization
                if user not in ALLOWED_USERS:
                    post_reply("⛔ Unauthorized. Commands are restricted.", msg_ts)
                    continue

                # Parse command
                cmd_text = text[1:].lower().strip()  # Remove ! prefix

                # Find matching command
                matched = False
                for cmd, info in COMMANDS.items():
                    if cmd_text == cmd or cmd_text.startswith(cmd + ' '):
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Running: !{cmd}")
                        handler = globals()[info['handler']]
                        handler(msg_ts)
                        matched = True
                        break

                if not matched:
                    post_reply(f"❓ Unknown command: `{text}`\nType `!help` for available commands.", msg_ts)

        except SlackApiError as e:
            print(f"Error: {e}")

    def run(self, poll_interval=3):
        """Main loop."""
        print("=" * 50)
        print("COMMAND BOT")
        print("=" * 50)
        print(f"Channel: #lucas-briefing")
        print(f"Prefix: !")
        print(f"Authorized users: {len(ALLOWED_USERS)}")
        print("-" * 50)

        # Mark existing messages as processed
        try:
            result = client.conversations_history(channel=COMMAND_CHANNEL, limit=50)
            for msg in result.get('messages', []):
                self.processed_messages.add(msg.get('ts'))
            print(f"Skipped {len(self.processed_messages)} existing messages")
        except Exception as e:
            print(f"Warning: {e}")

        print("Listening for commands...")

        while True:
            try:
                self.check_for_commands()
                time.sleep(poll_interval)
            except KeyboardInterrupt:
                print("\nBot stopped.")
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(poll_interval)


if __name__ == '__main__':
    bot = CommandBot()
    bot.run()

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
import json
import subprocess
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Usage tracking
USAGE_FILE = "/Users/lucaswillett/projects/support-memory/command_usage.json"

def load_usage():
    """Load command usage counts."""
    try:
        with open(USAGE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_usage(usage):
    """Save command usage counts."""
    try:
        with open(USAGE_FILE, 'w') as f:
            json.dump(usage, f, indent=2)
    except Exception:
        pass

def track_usage(cmd):
    """Increment usage count for a command."""
    usage = load_usage()
    usage[cmd] = usage.get(cmd, 0) + 1
    save_usage(usage)

# Config
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
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
    "heartbeat": {
        "description": "Send daily check-in with tasks and capture prompt",
        "handler": "cmd_heartbeat",
    },
    "gtasks": {
        "description": "Show open Google Tasks",
        "handler": "cmd_gtasks",
    },
    "done": {
        "description": "Complete a task by name (e.g., !done zendesk)",
        "handler": "cmd_done_task",
    },
    "add": {
        "description": "Add a new Google Task (e.g., !add Review Q1 metrics)",
        "handler": "cmd_add_task",
    },
    "zaps": {
        "description": "Show Zapier status (requires saved session)",
        "handler": "cmd_zaps",
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
    """Show help, sorted by usage frequency."""
    usage = load_usage()

    # Sort commands by usage (most used first)
    sorted_cmds = sorted(
        COMMANDS.items(),
        key=lambda x: usage.get(x[0], 0),
        reverse=True
    )

    help_text = "*Available Commands:*\n\n"
    for cmd, info in sorted_cmds:
        count = usage.get(cmd, 0)
        freq = f" _({count})_" if count > 0 else ""
        help_text += f"`!{cmd}` - {info['description']}{freq}\n"
    help_text += "\n_Sorted by usage. Commands only work for authorized users._"
    post_reply(help_text, thread_ts)


def cmd_heartbeat(thread_ts):
    """Send heartbeat check-in."""
    output = run_script(f"{SUPPORT_MEMORY_DIR}/heartbeat.py", ["heartbeat"], timeout=30)
    post_reply("💓 Heartbeat sent to channel.", thread_ts)


def cmd_gtasks(thread_ts):
    """Show open Google Tasks by category."""
    try:
        import sys
        sys.path.insert(0, SUPPORT_MEMORY_DIR)
        from google_tasks import get_all_tasks_by_category

        categories = get_all_tasks_by_category()
        if categories:
            total = sum(len(t) for t in categories.values())
            output = f"*📋 Google Tasks* ({total} across {len(categories)} categories)\n\n"

            for cat_name, tasks in categories.items():
                output += f"*{cat_name}* ({len(tasks)})\n"
                for t in tasks[:3]:
                    title = t['title'][:45]
                    if 'http' in title:
                        title = title.split('http')[0].strip() + '...'
                    output += f"  • {title}\n"
                if len(tasks) > 3:
                    output += f"  _+{len(tasks) - 3} more_\n"
                output += "\n"

            post_reply(output, thread_ts)
        else:
            post_reply("No open Google Tasks.", thread_ts)
    except Exception as e:
        post_reply(f"Error fetching tasks: {e}", thread_ts)


def cmd_done_task(thread_ts, search_text=None):
    """Complete a task by partial title match."""
    if not search_text:
        post_reply("Usage: `!done [search term]`\nExample: `!done zendesk` to complete task containing 'zendesk'", thread_ts)
        return

    try:
        import sys
        sys.path.insert(0, SUPPORT_MEMORY_DIR)
        from google_tasks import complete_task_by_title, find_task_by_title

        # First show what we found
        task, list_id = find_task_by_title(search_text)
        if not task:
            post_reply(f"❌ No task found matching '{search_text}'", thread_ts)
            return

        # Complete it
        result = complete_task_by_title(search_text)
        if result:
            post_reply(f"✅ Completed: *{task['title'][:60]}*", thread_ts)
        else:
            post_reply(f"❌ Error completing task", thread_ts)
    except Exception as e:
        post_reply(f"Error: {e}", thread_ts)


def cmd_add_task(thread_ts, task_title=None):
    """Add a new Google Task."""
    if not task_title:
        post_reply("Usage: `!add [task title]`\nExample: `!add Review Q1 metrics`", thread_ts)
        return

    try:
        import sys
        sys.path.insert(0, SUPPORT_MEMORY_DIR)
        from google_tasks import create_task

        result = create_task(task_title)
        if result:
            post_reply(f"✅ Added task: *{task_title}*", thread_ts)
        else:
            post_reply(f"❌ Error adding task", thread_ts)
    except Exception as e:
        post_reply(f"Error: {e}", thread_ts)


def cmd_zaps(thread_ts):
    """Show Zapier status via Playwright."""
    post_reply("🔌 Checking Zapier status...", thread_ts)
    try:
        import sys
        sys.path.insert(0, f"{SUPPORT_MEMORY_DIR}/browser")
        from zapier_status import get_zap_status, format_for_slack

        results = get_zap_status()
        output = format_for_slack(results)
        post_reply(output, thread_ts)
    except Exception as e:
        post_reply(f"Error: {e}\n\nTo set up: `python session_manager.py save zapier`", thread_ts)


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
                        track_usage(cmd)  # Track usage for sorting
                        handler = globals()[info['handler']]
                        # Extract arguments (everything after the command)
                        args = cmd_text[len(cmd):].strip() if cmd_text.startswith(cmd + ' ') else None
                        if args and cmd in ['done', 'add']:
                            handler(msg_ts, args)
                        else:
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

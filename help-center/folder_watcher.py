#!/usr/bin/env python3
"""
Folder Watcher for Help Center Article Pipeline

Monitors Google Drive folders for article movement and sends Slack notifications
to the appropriate SME when articles move to their review stage.

Run every 15 minutes via cron or launchd.
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from googleapiclient.discovery import build
from google_auth import get_credentials
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Config
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN', '***REDACTED***')
STATE_FILE = Path(__file__).parent / "watcher_state.json"

# Spreadsheet IDs
PIPELINE_SPREADSHEET_ID = "1tBLLpwxDcsaYwnGgfGtKvntKOVPj4EdY1p8rNesnvPA"
TAXONOMY_SPREADSHEET_ID = "1FiXiSrjJy5nvPt_qAOp2jhwZHhOvAOE76yoK5nt-KJ4"

# Folder IDs (from google_drive_sync.py)
FOLDER_IDS = {
    "0 - Drafts": "1jx653TlG_NPzHHyyk_rAka9s8dluACiA",
    "1 - SME Review": "1xKpuPlucCLxPytqNu-3tdfQHoZFPzLtP",
    "2 - Support Updates": "12ikiGdMn2EKMQ1YAxTOjWTtM8isSR9R0",
    "3 - Marketing Review": "1wNwGG8NUorCBtxwiwTDfNcrTSHPPayI3",
    "4 - Ready to Publish": "1yDMs_ecqByCBAanoQPbOx8LVZNZH7Jg_",
    "5 - Published & Archived": "1f74pSNiYIddiRIq9pivfT3RfRGwqwAnj",
}

# Reverse lookup: folder ID to stage name
FOLDER_TO_STAGE = {v: k for k, v in FOLDER_IDS.items()}

# SME name to Slack user mapping
# Format: "SME Name": "slack_user_id" or "first.last" (will be looked up)
# For testing, only Lucas gets notifications
SME_SLACK_MAPPING = {
    "lucas": "U9NLNTPDK",  # Lucas - for testing
    "support": "U9NLNTPDK",  # Route to Lucas for now
    "product": "U9NLNTPDK",  # Route to Lucas for now
    "tbd": "U9NLNTPDK",
    # Add real mappings later:
    # "jenny": "UXXXXXXXX",
    # "christian": "UXXXXXXXX",
    # "carolann": "UXXXXXXXX",
}

# Test mode - only notify Lucas
TEST_MODE = True
TEST_USER_ID = "U9NLNTPDK"  # Lucas

slack_client = WebClient(token=SLACK_BOT_TOKEN)


def get_drive_service():
    creds = get_credentials()
    if not creds:
        return None
    return build('drive', 'v3', credentials=creds)


def get_sheets_service():
    creds = get_credentials()
    if not creds:
        return None
    return build('sheets', 'v4', credentials=creds)


def load_state():
    """Load previous state of file locations."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state):
    """Save current state of file locations."""
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_files_in_folders():
    """Get all markdown files in pipeline folders with their locations."""
    service = get_drive_service()
    if not service:
        return {}

    files = {}
    for stage_name, folder_id in FOLDER_IDS.items():
        try:
            results = service.files().list(
                q=f"'{folder_id}' in parents and mimeType='text/markdown' and trashed=false",
                fields="files(id, name, modifiedTime)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()

            for f in results.get('files', []):
                files[f['id']] = {
                    'name': f['name'],
                    'stage': stage_name,
                    'modified': f['modifiedTime']
                }
        except Exception as e:
            print(f"Error listing {stage_name}: {e}")

    return files


def get_sme_for_article(article_title):
    """Look up the assigned SME from the tracking sheet."""
    service = get_sheets_service()
    if not service:
        return None

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=PIPELINE_SPREADSHEET_ID,
            range='A:C'  # Article Topic, Priority, Assigned SME
        ).execute()

        rows = result.get('values', [])
        for row in rows[1:]:  # Skip header
            if len(row) >= 3 and article_title.lower() in row[0].lower():
                return row[2]  # Assigned SME column
    except Exception as e:
        print(f"Error looking up SME: {e}")

    return None


def get_slack_user_for_sme(sme_name):
    """Get Slack user ID for an SME."""
    if TEST_MODE:
        return TEST_USER_ID

    # Normalize SME name
    sme_lower = sme_name.lower().strip()

    # Direct lookup
    if sme_lower in SME_SLACK_MAPPING:
        return SME_SLACK_MAPPING[sme_lower]

    # Try to extract name from format like "Product (CarolAnn)"
    if '(' in sme_name and ')' in sme_name:
        name = sme_name.split('(')[1].split(')')[0].lower()
        if name in SME_SLACK_MAPPING:
            return SME_SLACK_MAPPING[name]

    return None


def update_tracking_sheet_status(article_name, new_status):
    """Update the status in the tracking spreadsheet."""
    service = get_sheets_service()
    if not service:
        return False

    try:
        # Find the row with this article
        result = service.spreadsheets().values().get(
            spreadsheetId=PIPELINE_SPREADSHEET_ID,
            range='A:E'  # Need to find the row
        ).execute()

        rows = result.get('values', [])
        for i, row in enumerate(rows[1:], start=2):  # Start at row 2 (1-indexed, skip header)
            if len(row) >= 1:
                # Match by article name (might be partial match)
                article_title = article_name.replace('.md', '').split(' - ', 1)[-1] if ' - ' in article_name else article_name
                if article_title.lower()[:30] in row[0].lower() or row[0].lower()[:30] in article_title.lower():
                    # Update status in column E
                    service.spreadsheets().values().update(
                        spreadsheetId=PIPELINE_SPREADSHEET_ID,
                        range=f'E{i}',
                        valueInputOption='USER_ENTERED',
                        body={'values': [[new_status]]}
                    ).execute()
                    print(f"  Updated sheet: {row[0][:30]}... → {new_status}")
                    return True
    except Exception as e:
        print(f"Error updating sheet: {e}")

    return False


def send_slack_notification(user_id, article_name, new_stage, file_id):
    """Send a Slack DM notification about an article moving."""
    try:
        # Clean up article name for display
        display_name = article_name.replace('.md', '')
        if ' - ' in display_name:
            display_name = display_name.split(' - ', 1)[1]

        drive_link = f"https://drive.google.com/file/d/{file_id}/view"

        message = f"*Article Pipeline Update*\n\n"
        message += f"An article has moved to *{new_stage}*:\n"
        message += f"> {display_name}\n\n"
        message += f"<{drive_link}|Open in Google Drive>"

        # Add stage-specific instructions
        if "SME Review" in new_stage:
            message += "\n\n_Please review for technical accuracy and completeness._"
        elif "Marketing Review" in new_stage:
            message += "\n\n_Please review for tone, branding, and clarity._"
        elif "Ready to Publish" in new_stage:
            message += "\n\n_This article is approved and ready to be published to Zendesk._"

        # Open DM channel and send
        dm = slack_client.conversations_open(users=[user_id])
        channel_id = dm['channel']['id']

        slack_client.chat_postMessage(
            channel=channel_id,
            text=message
        )
        print(f"  Notified user {user_id} about {display_name[:30]}...")
        return True

    except SlackApiError as e:
        print(f"  Slack notification error: {e}")
        return False


def check_for_moves():
    """Main function: check for file moves and send notifications."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Checking for article moves...")

    # Load previous state
    prev_state = load_state()

    # Get current file locations
    current_files = get_files_in_folders()

    if not current_files:
        print("  No files found or Drive connection failed")
        return

    moves_detected = 0

    # Compare with previous state
    for file_id, current_info in current_files.items():
        if file_id in prev_state:
            prev_stage = prev_state[file_id].get('stage')
            curr_stage = current_info['stage']

            if prev_stage != curr_stage:
                moves_detected += 1
                print(f"  Move detected: {current_info['name']}")
                print(f"    {prev_stage} → {curr_stage}")

                # Update tracking sheet
                update_tracking_sheet_status(current_info['name'], curr_stage)

                # Get SME and send notification
                sme = get_sme_for_article(current_info['name'])
                if sme:
                    user_id = get_slack_user_for_sme(sme)
                    if user_id:
                        send_slack_notification(user_id, current_info['name'], curr_stage, file_id)
                    else:
                        print(f"    No Slack user found for SME: {sme}")
                else:
                    # Notify default (Lucas) if no SME assigned
                    if TEST_MODE:
                        send_slack_notification(TEST_USER_ID, current_info['name'], curr_stage, file_id)

    # Save current state for next run
    save_state({fid: info for fid, info in current_files.items()})

    if moves_detected == 0:
        print("  No moves detected")
    else:
        print(f"  {moves_detected} move(s) processed")


def show_status():
    """Show current state of all files in pipeline."""
    current_files = get_files_in_folders()

    print("\nCurrent Pipeline Status:")
    print("-" * 60)

    for stage_name in FOLDER_IDS.keys():
        files_in_stage = [f for f in current_files.values() if f['stage'] == stage_name]
        print(f"\n{stage_name}: ({len(files_in_stage)} files)")
        for f in files_in_stage:
            display_name = f['name'].replace('.md', '')
            if ' - ' in display_name:
                display_name = display_name.split(' - ', 1)[1]
            print(f"  - {display_name[:50]}")


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'status':
        show_status()
    else:
        check_for_moves()

#!/usr/bin/env python3
"""
Google Drive & Sheets integration for Help Center Article Pipeline.

Syncs article drafts to Google Drive folders and tracks them in the pipeline spreadsheet.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth import get_credentials

# Google Drive folder IDs
PARENT_FOLDER_ID = "1jpgmL5YKrznCFagaq3121e3gwKfqnRYK"  # Help Center Articles folder

# Folder name to ID mapping (exact names from Drive)
FOLDER_IDS = {
    "0 - Drafts": "1jx653TlG_NPzHHyyk_rAka9s8dluACiA",
    "1 - SME Review": "1xKpuPlucCLxPytqNu-3tdfQHoZFPzLtP",
    "2 - Support Updates": "12ikiGdMn2EKMQ1YAxTOjWTtM8isSR9R0",
    "3 - Marketing Review": "1wNwGG8NUorCBtxwiwTDfNcrTSHPPayI3",
    "4 - Ready to Publish": "1yDMs_ecqByCBAanoQPbOx8LVZNZH7Jg_",
    "5 - Published & Archived": "1f74pSNiYIddiRIq9pivfT3RfRGwqwAnj",
}

# Simplified stage names for CLI
STAGE_ALIASES = {
    "drafts": "0 - Drafts",
    "sme": "1 - SME Review",
    "support": "2 - Support Updates",
    "marketing": "3 - Marketing Review",
    "ready": "4 - Ready to Publish",
    "published": "5 - Published & Archived",
}

# Tracking spreadsheet
PIPELINE_SPREADSHEET_ID = "1tBLLpwxDcsaYwnGgfGtKvntKOVPj4EdY1p8rNesnvPA"
TAXONOMY_SPREADSHEET_ID = "1FiXiSrjJy5nvPt_qAOp2jhwZHhOvAOE76yoK5nt-KJ4"


def get_drive_service():
    """Get authenticated Drive API service."""
    creds = get_credentials()
    if not creds:
        return None
    return build('drive', 'v3', credentials=creds)


def get_sheets_service():
    """Get authenticated Sheets API service."""
    creds = get_credentials()
    if not creds:
        return None
    return build('sheets', 'v4', credentials=creds)


def get_folder_ids():
    """Get or create folder IDs for the pipeline stages."""
    global FOLDER_IDS

    service = get_drive_service()
    if not service:
        print("Could not connect to Google Drive")
        return None

    # List folders in parent (support shared drives)
    results = service.files().list(
        q=f"'{PARENT_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()

    existing_folders = {f['name']: f['id'] for f in results.get('files', [])}

    # Map existing folders
    for folder_name in FOLDER_IDS:
        if folder_name in existing_folders:
            FOLDER_IDS[folder_name] = existing_folders[folder_name]

    # Create "0 - Drafts" if it doesn't exist
    if not FOLDER_IDS["0 - Drafts"]:
        folder_metadata = {
            'name': '0 - Drafts',
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [PARENT_FOLDER_ID]
        }
        folder = service.files().create(
            body=folder_metadata,
            fields='id',
            supportsAllDrives=True
        ).execute()
        FOLDER_IDS["0 - Drafts"] = folder.get('id')
        print(f"Created '0 - Drafts' folder: {folder.get('id')}")

    return FOLDER_IDS


def upload_draft_to_drive(local_file_path, article_id, title):
    """Upload a draft markdown file to the '0 - Drafts' folder."""
    service = get_drive_service()
    if not service:
        return None

    # Ensure we have folder IDs
    folders = get_folder_ids()
    if not folders or not folders.get("0 - Drafts"):
        print("Could not get Drafts folder ID")
        return None

    drafts_folder_id = folders["0 - Drafts"]

    # Clean up title for filename
    clean_title = "".join(c if c.isalnum() or c in ' -_' else '' for c in title)[:50]
    filename = f"{article_id} - {clean_title}.md"

    # Check if file already exists
    existing = service.files().list(
        q=f"name='{filename}' and '{drafts_folder_id}' in parents and trashed=false",
        fields="files(id)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()

    if existing.get('files'):
        # Update existing file
        file_id = existing['files'][0]['id']
        media = MediaFileUpload(local_file_path, mimetype='text/markdown')
        file = service.files().update(
            fileId=file_id,
            media_body=media,
            supportsAllDrives=True
        ).execute()
        print(f"  → Updated in Drive: {filename}")
        return file.get('id')
    else:
        # Create new file
        file_metadata = {
            'name': filename,
            'parents': [drafts_folder_id]
        }
        media = MediaFileUpload(local_file_path, mimetype='text/markdown')
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        ).execute()
        print(f"  → Uploaded to Drive: {filename}")
        return file.get('id')


def get_sme_from_taxonomy(topic):
    """Look up SME from taxonomy spreadsheet based on topic/category."""
    service = get_sheets_service()
    if not service:
        return "TBD"

    # Topic to taxonomy category mapping
    topic_to_category = {
        "Product - VMP": "Platform Features",
        "Product - SalesHub": "Platform Features",
        "Product - TrueTour": "Platform Features",
        "Onboarding": "Getting Started & Learning",
        "Billing & Account": "Account Management",
        "Integrations": "Platform Features",
        "Authentication & Access": "Account Management",
        "Domain & URLs": "Platform Features",
        "General": None,
    }

    category = topic_to_category.get(topic)
    if not category:
        return "TBD"

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=TAXONOMY_SPREADSHEET_ID,
            range='A:F'
        ).execute()

        rows = result.get('values', [])
        for row in rows[1:]:
            if len(row) >= 6 and row[0] == category:
                return row[5]  # SME column
    except Exception as e:
        print(f"  Taxonomy lookup error: {e}")

    # Fallback mapping if taxonomy lookup fails
    fallback = {
        "Product - VMP": "Product",
        "Product - SalesHub": "Product",
        "Product - TrueTour": "Product",
        "Onboarding": "CT&E (Tracy)",
        "Billing & Account": "Support",
        "Integrations": "Product",
        "Authentication & Access": "Support",
        "Domain & URLs": "Support",
        "General": "TBD",
    }
    return fallback.get(topic, "TBD")


def get_slack_username(user_id):
    """Look up Slack username from user ID."""
    try:
        from slack_sdk import WebClient
        client = WebClient(token=os.environ.get('SLACK_BOT_TOKEN', '***REDACTED***'))
        result = client.users_info(user=user_id)
        if result['ok']:
            profile = result['user']['profile']
            return profile.get('display_name') or profile.get('real_name') or user_id
    except:
        pass
    return user_id


def add_to_pipeline_sheet(article_id, title, submitter, topic, priority, slack_ts):
    """Add a new row to the pipeline tracking spreadsheet.

    Columns: Article Topic | Priority | Assigned SME | Submitted By | Status |
             Date Created | Google Doc Link | Date Published | Zendesk URL | Notes
    """
    service = get_sheets_service()
    if not service:
        return False

    now = datetime.now().strftime("%Y-%m-%d")
    drafts_folder_id = FOLDER_IDS.get('0 - Drafts', '')
    drive_link = f"https://drive.google.com/drive/folders/{drafts_folder_id}"

    # Get SME from taxonomy
    assigned_sme = get_sme_from_taxonomy(topic)

    # Get submitter's Slack display name
    submitter_name = get_slack_username(submitter)

    row = [
        title[:100],           # Article Topic
        priority,              # Priority
        assigned_sme,          # Assigned SME (from taxonomy)
        submitter_name,        # Submitted By (Slack user who requested)
        "0 - Draft",           # Status
        now,                   # Date Created
        drive_link,            # Google Doc Link
        "",                    # Date Published
        "",                    # Zendesk URL
        f"ID: {article_id} | Topic: {topic}"  # Notes
    ]

    try:
        body = {'values': [row]}
        result = service.spreadsheets().values().append(
            spreadsheetId=PIPELINE_SPREADSHEET_ID,
            range='A:J',
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body=body
        ).execute()

        print(f"  → Added to tracking sheet: {title[:40]}...")
        print(f"  → Assigned SME: {assigned_sme}")
        return True
    except Exception as e:
        print(f"  → Error adding to sheet: {e}")
        return False


def get_pipeline_stats():
    """Get current stats from the pipeline spreadsheet."""
    service = get_sheets_service()
    if not service:
        return None

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=PIPELINE_SPREADSHEET_ID,
            range='A:F'
        ).execute()

        rows = result.get('values', [])
        if not rows:
            return {'total': 0}

        # Count by status (assuming status is in column F)
        stats = {'total': len(rows) - 1}  # Exclude header
        for row in rows[1:]:  # Skip header
            if len(row) >= 6:
                status = row[5]
                stats[status] = stats.get(status, 0) + 1

        return stats
    except Exception as e:
        print(f"Error getting pipeline stats: {e}")
        return None


def move_file_to_folder(file_id, target_folder_name):
    """Move a file from one pipeline folder to another."""
    service = get_drive_service()
    if not service:
        return False

    folders = get_folder_ids()
    if not folders or target_folder_name not in folders:
        print(f"Unknown folder: {target_folder_name}")
        return False

    target_folder_id = folders[target_folder_name]

    try:
        # Get current parent
        file = service.files().get(
            fileId=file_id,
            fields='parents',
            supportsAllDrives=True
        ).execute()
        previous_parents = ",".join(file.get('parents', []))

        # Move file
        service.files().update(
            fileId=file_id,
            addParents=target_folder_id,
            removeParents=previous_parents,
            fields='id, parents',
            supportsAllDrives=True
        ).execute()

        print(f"Moved file to {target_folder_name}")
        return True
    except Exception as e:
        print(f"Error moving file: {e}")
        return False


def test_connection():
    """Test Drive and Sheets connection."""
    print("Testing Google Drive connection...")

    folders = get_folder_ids()
    if folders:
        print("✅ Drive connection successful")
        print("Folders found:")
        for name, fid in folders.items():
            status = "✓" if fid else "✗ (will create)"
            print(f"  {status} {name}")
    else:
        print("❌ Could not connect to Drive")
        return False

    print("\nTesting Sheets connection...")
    stats = get_pipeline_stats()
    if stats is not None:
        print("✅ Sheets connection successful")
        print(f"  Total articles tracked: {stats.get('total', 0)}")
    else:
        print("❌ Could not connect to Sheets")
        return False

    return True


if __name__ == '__main__':
    test_connection()

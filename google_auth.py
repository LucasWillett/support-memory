#!/usr/bin/env python3
"""
Google API Authentication for Support Memory.
Handles OAuth flow and token management for Calendar, Tasks, and Sheets.
"""

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Scopes needed for full integration
SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/tasks.readonly',
    'https://www.googleapis.com/auth/spreadsheets',  # Read + write to tracking sheet
    'https://www.googleapis.com/auth/drive',          # Access Drive folders and files
]

# File paths
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), 'credentials.json')
TOKEN_FILE = os.path.join(os.path.dirname(__file__), 'token.json')


def get_credentials():
    """Get valid Google API credentials, refreshing or re-authorizing as needed."""
    creds = None

    # Load existing token
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                print(f"Missing {CREDENTIALS_FILE}")
                print("Download OAuth credentials from Google Cloud Console")
                print("See GOOGLE_SETUP.md for instructions")
                return None

            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for next time
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return creds


def test_auth():
    """Test that authentication works."""
    creds = get_credentials()
    if creds:
        print("✅ Google authentication successful")
        print(f"Token saved to {TOKEN_FILE}")
        return True
    else:
        print("❌ Authentication failed")
        return False


if __name__ == '__main__':
    test_auth()

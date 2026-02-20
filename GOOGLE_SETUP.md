# Google API Setup for Support Memory

## Step 1: Create Google Cloud Project (or use existing)

1. Go to https://console.cloud.google.com
2. Create new project or select existing (e.g., "Support Memory")
3. Note the project ID

## Step 2: Enable APIs

Go to APIs & Services > Enable APIs and enable:
- Google Calendar API
- Google Tasks API
- Google Sheets API

## Step 3: Create OAuth Credentials

1. Go to APIs & Services > Credentials
2. Click "Create Credentials" > "OAuth client ID"
3. If prompted, configure OAuth consent screen:
   - User type: Internal (if using Workspace) or External
   - App name: "Support Memory"
   - Scopes: Add calendar, tasks, sheets scopes
4. Application type: "Desktop app"
5. Download the JSON file
6. Save as `credentials.json` in this directory

## Step 4: First Run Auth

Run this to authorize:
```bash
python3 google_auth.py
```

This opens a browser to authorize. Token saved to `token.json`.

## Required Scopes

- `https://www.googleapis.com/auth/calendar.readonly` (read calendar)
- `https://www.googleapis.com/auth/calendar.events` (create/edit events)
- `https://www.googleapis.com/auth/tasks.readonly` (read tasks)
- `https://www.googleapis.com/auth/spreadsheets.readonly` (read Q1 spreadsheet)

## Files Created

- `credentials.json` - OAuth client credentials (don't commit)
- `token.json` - Your auth token (don't commit)

Both are in .gitignore.

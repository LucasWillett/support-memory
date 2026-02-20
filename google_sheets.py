#!/usr/bin/env python3
"""
Google Sheets integration for Support Memory.
Monitors Q1 Support Team Project Tracker and linked docs.
"""

import re
from googleapiclient.discovery import build
from google_auth import get_credentials

# Q1 Support Project Tracker
Q1_SPREADSHEET_ID = "1GMIBZYpkYghgWbrdzuxf7GZBQnRfegK5yw2mH_384Rs"
Q1_SHEET_GID = "292880445"

# GTM Project Tracking (canonical deadlines)
GTM_SPREADSHEET_ID = "1tE8MjoKgReHosmjksADzcJqCRXto90G4-ShBHJWCy9s"
GTM_TAB = "Spring GTM-UX MVP"


def get_sheets_service():
    """Get authenticated Sheets API service."""
    creds = get_credentials()
    if not creds:
        return None
    return build('sheets', 'v4', credentials=creds)


def get_spreadsheet_data(spreadsheet_id=Q1_SPREADSHEET_ID, range_name='A:Z'):
    """Get data from a spreadsheet."""
    service = get_sheets_service()
    if not service:
        return []

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name
        ).execute()
        return result.get('values', [])
    except Exception as e:
        print(f"Error reading spreadsheet: {e}")
        return []


def get_q1_projects():
    """Get projects from Q1 tracker with their status and linked docs."""
    rows = get_spreadsheet_data(Q1_SPREADSHEET_ID)
    if not rows:
        return []

    projects = []
    headers = rows[0] if rows else []

    # Find column indices
    def find_col(names):
        for name in names:
            for i, h in enumerate(headers):
                if name.lower() in h.lower():
                    return i
        return -1

    col_project = find_col(['project', 'name', 'initiative'])
    col_status = find_col(['status', 'state'])
    col_owner = find_col(['owner', 'assigned', 'lead'])
    col_due = find_col(['due', 'deadline', 'date'])
    col_link_e = 4  # Column E (0-indexed)
    col_link_f = 5  # Column F (0-indexed)

    for row in rows[1:]:  # Skip header
        if len(row) <= col_project or not row[col_project].strip():
            continue

        project = {
            'name': row[col_project] if col_project >= 0 and len(row) > col_project else '',
            'status': row[col_status] if col_status >= 0 and len(row) > col_status else '',
            'owner': row[col_owner] if col_owner >= 0 and len(row) > col_owner else '',
            'due': row[col_due] if col_due >= 0 and len(row) > col_due else '',
            'linked_docs': [],
        }

        # Extract links from columns E and F
        for col_idx in [col_link_e, col_link_f]:
            if len(row) > col_idx and row[col_idx]:
                links = extract_doc_links(row[col_idx])
                project['linked_docs'].extend(links)

        if project['name']:
            projects.append(project)

    return projects


def extract_doc_links(cell_value):
    """Extract Google Doc/Sheet links from a cell."""
    links = []
    # Match Google Docs/Sheets URLs
    pattern = r'https://docs\.google\.com/(?:document|spreadsheets)/d/([a-zA-Z0-9_-]+)'
    matches = re.findall(pattern, str(cell_value))
    for doc_id in matches:
        links.append({
            'type': 'document' if 'document' in cell_value else 'spreadsheet',
            'id': doc_id,
            'url': f"https://docs.google.com/document/d/{doc_id}" if 'document' in cell_value else f"https://docs.google.com/spreadsheets/d/{doc_id}"
        })
    return links


def get_open_projects():
    """Get projects that aren't complete."""
    projects = get_q1_projects()
    open_projects = []

    closed_statuses = ['complete', 'done', 'closed', 'cancelled', 'canceled']

    for p in projects:
        status_lower = p['status'].lower() if p['status'] else ''
        if not any(s in status_lower for s in closed_statuses):
            open_projects.append(p)

    return open_projects


def get_my_projects(my_name='lucas'):
    """Get projects owned by me."""
    projects = get_open_projects()
    return [p for p in projects if my_name.lower() in p['owner'].lower()]


def format_for_briefing(projects, max_items=5):
    """Format projects for morning briefing."""
    lines = []
    for p in projects[:max_items]:
        status = f" [{p['status']}]" if p['status'] else ""
        due = f" (due: {p['due']})" if p['due'] else ""
        lines.append(f"• {p['name']}{status}{due}")

    if len(projects) > max_items:
        lines.append(f"  _...plus {len(projects) - max_items} more_")

    return "\n".join(lines)


def get_gtm_items(assignee_filter=None):
    """Get GTM tracking items, optionally filtered by assignee."""
    service = get_sheets_service()
    if not service:
        return []

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=GTM_SPREADSHEET_ID,
            range=f"'{GTM_TAB}'!A:H"
        ).execute()

        rows = result.get('values', [])
        if not rows:
            return []

        items = []
        for row in rows[1:]:  # Skip header
            if len(row) < 2:
                continue

            status = row[0] if len(row) > 0 else ''
            task = row[1] if len(row) > 1 else ''
            assignee = row[4] if len(row) > 4 else ''
            description = row[5] if len(row) > 5 else ''
            due = row[6] if len(row) > 6 else ''

            # Skip completed items
            if 'complete' in status.lower():
                continue

            # Filter by assignee if specified
            if assignee_filter:
                if assignee_filter.lower() not in assignee.lower():
                    continue

            items.append({
                'status': status,
                'task': task,
                'assignee': assignee,
                'description': description,
                'due': due,
            })

        return items

    except Exception as e:
        print(f"Error fetching GTM items: {e}")
        return []


def get_my_gtm_items():
    """Get GTM items assigned to Lucas or Support."""
    all_items = get_gtm_items()
    my_items = []

    for item in all_items:
        assignee_lower = item['assignee'].lower()
        if 'lucas' in assignee_lower or 'support' in assignee_lower:
            my_items.append(item)

    return my_items


if __name__ == '__main__':
    print("=== Q1 Support Project Tracker ===\n")

    projects = get_q1_projects()
    if not projects:
        print("No projects found (or not authenticated)")
        print(f"Spreadsheet ID: {Q1_SPREADSHEET_ID}")
    else:
        print(f"Found {len(projects)} projects\n")

        open_projects = get_open_projects()
        print(f"Open projects: {len(open_projects)}")

        my_projects = get_my_projects('lucas')
        print(f"Lucas's projects: {len(my_projects)}\n")

        if my_projects:
            print("Your projects:")
            print(format_for_briefing(my_projects))

        print("\n=== All Open Projects ===")
        for p in open_projects[:10]:
            print(f"  {p['name']}")
            if p['status']:
                print(f"    Status: {p['status']}")
            if p['owner']:
                print(f"    Owner: {p['owner']}")
            if p['linked_docs']:
                print(f"    Linked docs: {len(p['linked_docs'])}")

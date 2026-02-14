#!/usr/bin/env python3
"""
Sync ticket patterns from Zendesk dashboard to shared memory.
Run locally after weekly summary, or on demand.

Usage:
  python3 sync_from_zendesk.py
"""
import json
import requests
from datetime import datetime
from shared_memory import load_memory, save_memory, update_customer

DASHBOARD_URL = "https://lucaswillett.github.io/zendesk-dashboard/index.html"
# We'll fetch the data.json that powers the dashboard
DATA_URL = "https://raw.githubusercontent.com/LucasWillett/zendesk-dashboard/main/data.json"


def fetch_dashboard_data():
    """Fetch latest data from the Zendesk dashboard."""
    import sys
    sys.path.insert(0, '/Users/lucaswillett/projects/zendesk-dashboard')

    try:
        from update_dashboard import get_ticket_data
        print("  → Fetching from Zendesk API...")
        return get_ticket_data()
    except Exception as e:
        print(f"  → Error fetching from Zendesk: {e}")

    return None


def sync_patterns():
    """Sync ticket patterns to shared memory."""
    print("Syncing ticket patterns to shared memory...")

    data = fetch_dashboard_data()
    if not data:
        print("  → Could not fetch dashboard data")
        return False

    mem = load_memory()

    # Extract patterns from this week's tickets
    week_data = data.get('week', {})
    beta_tickets = week_data.get('beta_tickets', [])

    if not beta_tickets:
        print("  → No beta tickets this week")
        return True

    # Group by customer/account
    customer_issues = {}
    for ticket in beta_tickets:
        account = ticket.get('account', 'Unknown')
        if account not in customer_issues:
            customer_issues[account] = {
                'tickets': 0,
                'tags': [],
                'subjects': []
            }
        customer_issues[account]['tickets'] += 1
        customer_issues[account]['tags'].extend(ticket.get('beta_tags', []))
        customer_issues[account]['subjects'].append(ticket.get('subject', ''))

    # Update customer patterns in memory
    today = datetime.now().strftime("%Y-%m-%d")
    patterns_updated = 0

    for account, issues in customer_issues.items():
        # Determine sentiment based on ticket count
        if issues['tickets'] >= 3:
            sentiment = 'frustrated'
        elif issues['tickets'] >= 2:
            sentiment = 'concerned'
        else:
            sentiment = 'neutral'

        # Check if pattern already exists for this customer
        existing = None
        for i, pat in enumerate(mem.get('customer_patterns', [])):
            if pat.get('customer', '').lower() == account.lower():
                existing = i
                break

        pattern = {
            'customer': account,
            'last_updated': today,
            'recent_tickets': issues['tickets'],
            'sentiment': sentiment,
            'notes': f"Tags: {', '.join(set(issues['tags']))}"
        }

        if existing is not None:
            mem['customer_patterns'][existing] = pattern
        else:
            mem['customer_patterns'].append(pattern)

        patterns_updated += 1
        print(f"  → {account}: {issues['tickets']} tickets, sentiment={sentiment}")

    save_memory(mem)
    print(f"\nSynced {patterns_updated} customer patterns to shared memory")
    return True


def log_weekly_summary(week_beta, week_pct, tags_summary):
    """Log this week's summary as a decision/observation."""
    mem = load_memory()

    today = datetime.now().strftime("%Y-%m-%d")
    tags_str = ", ".join([f"{count} {tag}" for tag, count in tags_summary.items()])

    mem['decisions'].append({
        'date': today,
        'topic': 'Weekly ticket summary',
        'decision': f"{week_beta} beta tickets ({week_pct}% of total)",
        'rationale': f"Tags: {tags_str}" if tags_str else "No specific tags"
    })

    save_memory(mem)
    print(f"Logged weekly summary to decisions")


if __name__ == "__main__":
    sync_patterns()

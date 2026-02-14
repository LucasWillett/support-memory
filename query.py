#!/usr/bin/env python3
"""
Query the support memory - simple CLI for searching and summarizing.

Usage:
  python3 query.py                    # Show summary
  python3 query.py search <term>      # Search observations
  python3 query.py customer <name>    # Get customer context
  python3 query.py themes             # Show theme breakdown
  python3 query.py recent [n]         # Show n most recent observations
"""
import sys
import json
from datetime import datetime
from shared_memory import load_memory, load_entities, get_customer_context


def show_summary():
    """Show overall memory summary."""
    mem = load_memory()
    ent = load_entities()

    print("=" * 50)
    print("SUPPORT MEMORY SUMMARY")
    print("=" * 50)

    print(f"\nIncidents logged: {len(mem.get('incidents', []))}")
    print(f"Customer patterns: {len(mem.get('customer_patterns', []))}")
    print(f"Decisions logged: {len(mem.get('decisions', []))}")
    print(f"Observations: {len(mem.get('observations', []))}")
    print(f"Entities tracked: {len(ent.get('customers', {})) + len(ent.get('projects', {}))}")

    # Theme breakdown
    themes = {}
    channels = {}
    for obs in mem.get('observations', []):
        for t in obs.get('themes', []):
            themes[t] = themes.get(t, 0) + 1
        ch = obs.get('channel', 'unknown')
        channels[ch] = channels.get(ch, 0) + 1

    if themes:
        print("\nTop themes:")
        for t, c in sorted(themes.items(), key=lambda x: -x[1])[:5]:
            print(f"  {t}: {c}")

    if channels:
        print("\nBy channel:")
        for ch, c in sorted(channels.items(), key=lambda x: -x[1])[:5]:
            print(f"  #{ch}: {c}")


def search_observations(term):
    """Search observations for a term."""
    mem = load_memory()
    term_lower = term.lower()

    results = []
    for obs in mem.get('observations', []):
        snippet = obs.get('snippet', '').lower()
        if term_lower in snippet:
            results.append(obs)

    print(f"Found {len(results)} observations matching '{term}':\n")
    for obs in results[-10:]:  # Last 10 matches
        print(f"[{obs.get('date')} #{obs.get('channel')}]")
        print(f"  {obs.get('snippet', '')[:150]}...")
        if obs.get('themes'):
            print(f"  Themes: {', '.join(obs['themes'])}")
        print()


def show_customer(name):
    """Show all context for a customer."""
    ctx = get_customer_context(name)

    print(f"=== Context for '{name}' ===\n")

    if ctx.get('entity'):
        print("Entity:")
        print(f"  Name: {ctx['entity'].get('name')}")
        print(f"  Health: {ctx['entity'].get('health', 'unknown')}")
        print(f"  Last contact: {ctx['entity'].get('last_contact')}")
    else:
        print("No entity record found.")

    if ctx.get('incidents'):
        print(f"\nIncidents ({len(ctx['incidents'])}):")
        for inc in ctx['incidents']:
            print(f"  [{inc.get('date')}] {inc.get('summary')}")

    if ctx.get('patterns'):
        print(f"\nPatterns:")
        for pat in ctx['patterns']:
            print(f"  Tickets: {pat.get('recent_tickets')} | Sentiment: {pat.get('sentiment')}")
            print(f"  Notes: {pat.get('notes')}")


def show_themes():
    """Show detailed theme breakdown."""
    mem = load_memory()

    themes = {}
    for obs in mem.get('observations', []):
        for t in obs.get('themes', []):
            if t not in themes:
                themes[t] = {'count': 0, 'examples': []}
            themes[t]['count'] += 1
            if len(themes[t]['examples']) < 3:
                themes[t]['examples'].append(obs.get('snippet', '')[:100])

    print("=== Theme Analysis ===\n")
    for t, data in sorted(themes.items(), key=lambda x: -x[1]['count']):
        print(f"{t}: {data['count']} occurrences")
        for ex in data['examples']:
            print(f"  • {ex}...")
        print()


def show_recent(n=10):
    """Show n most recent observations."""
    mem = load_memory()
    obs_list = mem.get('observations', [])[-n:]

    print(f"=== Last {len(obs_list)} Observations ===\n")
    for obs in reversed(obs_list):
        print(f"[{obs.get('date')} {obs.get('time')} #{obs.get('channel')}]")
        print(f"  {obs.get('snippet', '')[:120]}...")
        if obs.get('themes'):
            print(f"  Themes: {', '.join(obs['themes'])}")
        print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        show_summary()
    elif sys.argv[1] == "search" and len(sys.argv) > 2:
        search_observations(" ".join(sys.argv[2:]))
    elif sys.argv[1] == "customer" and len(sys.argv) > 2:
        show_customer(" ".join(sys.argv[2:]))
    elif sys.argv[1] == "themes":
        show_themes()
    elif sys.argv[1] == "recent":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        show_recent(n)
    else:
        print(__doc__)

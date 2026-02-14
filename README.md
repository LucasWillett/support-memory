# Support Memory

A shared memory and multi-voice advisory system for Support intelligence.

## What's Here

```
support-memory/
├── memory.json           # Shared context (incidents, patterns, decisions, observations)
├── entities.json         # Tracked customers and projects
├── shared_memory.py      # Read/write helpers for other bots
├── slack_listener.py     # Reads from Slack channels → memory (runs as service)
├── sync_from_zendesk.py  # Syncs ticket patterns from Zendesk dashboard
├── query.py              # CLI to search and summarize memory
├── council.py            # Multi-voice advisory (Support, GTM, CSM, Training, Help Center)
└── voices/               # Persona definitions for each voice
    ├── support.md
    ├── gtm.md
    ├── csm.md
    ├── training.md
    └── help_center.md
```

## Quick Commands

```bash
# Summary of memory state
python3 query.py

# Search observations
python3 query.py search "truetour"

# Get customer context
python3 query.py customer "Acme Corp"

# Theme breakdown
python3 query.py themes

# Recent observations
python3 query.py recent 20

# Ask the council a question
python3 council.py "Should we launch feature X?"
```

## Services Running

**Slack Listener** (launchd)
- Service: `com.supportmemory.slack-listener`
- Logs: `logs/slack-listener.log`
- Monitors 14 Slack channels, writes observations to memory

```bash
# Check status
launchctl list | grep slack-listener

# View logs
tail -f logs/slack-listener.log

# Restart
launchctl stop com.supportmemory.slack-listener
launchctl start com.supportmemory.slack-listener
```

## Pending Setup

1. **IT: Reinstall Slack bot** - `groups:read` scope was added, needs reinstall to activate
2. **Private channels** - After reinstall, `/invite @ChurnZero Bot` to #gtm-weekly, #cx-external, #cx-internal
3. **GA4 permissions** - IT ticket IIT-1244 for ChurnZero bot platform queries

## How Other Bots Connect

```python
# In any bot, add this:
import sys
sys.path.insert(0, '/Users/lucaswillett/projects/support-memory')
from shared_memory import get_customer_context, log_incident, log_decision

# Check context before responding
ctx = get_customer_context("Customer Name")
if ctx['incidents']:
    # Customer had recent incidents

# Log decisions/incidents
log_incident("p1-2026-02-14", "Description", ["affected customers"])
log_decision("Topic", "What was decided", "Why")
```

## Architecture

```
[Slack Channels] ──→ [Slack Listener] ──→ [memory.json] ←── [Other Bots]
[Zendesk]        ──→ [Sync Script]    ──→     ↓
                                          [Council]
                                              ↓
                                      [Multi-voice advice]
```

## The Team

**Anchor** (Claude Code) - Terminal agent. Builds systems, writes code, maintains memory. Holds position.

**Scout** (Browser Claude) - Web agent. Explores, researches, executes remote tasks. Reports back.

Relay: http://localhost:5002

---
Built 2026-02-13

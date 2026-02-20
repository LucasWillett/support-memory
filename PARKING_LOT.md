# Parking Lot

Ideas worth keeping but not actively pursuing.

---

## MCP Servers for Direct API Integrations
**Added:** 2026-02-17
**Why parked:** Works fine with current bot architecture. MCP is cleaner but doesn't save tokens significantly. Revisit when MCP ecosystem matures.
**What it would do:** Give Claude direct access to ChurnZero, Google Sheets, Zendesk, etc. via Model Context Protocol instead of Python scripts.

---

## File-Based Relay for Anchor/Scout
**Added:** 2026-02-17
**Why parked:** Playwright now handles browser tasks directly, reducing need for Scout relay. HTTP relay (localhost:5002) still works when needed.
**What it would do:** Replace HTTP relay with file-based queue (JSON files in watched folders). Simpler, debuggable, survives restarts.

---

## AI Scheduling Assistant (Gmail → Calendar)
**Added:** 2026-02-17
**Why parked:** Slack-heavy workflow, not Gmail-heavy. Cool tech but adds Vercel infra to maintain. Team still ramping on Claude basics.
**Source:** External share - "Hand this to Claude Code and say 'Build this for me'"

**What it does:**
- Monitors Gmail every 5 min for scheduling requests
- Uses Claude to classify emails and draft replies with open time slots
- Checks Google Calendar (including colleagues' FreeBusy)
- Auto-books calendar events when time is confirmed in thread
- Drafts appear in Gmail for review before sending

**Stack:** Next.js 15, Anthropic Claude SDK, Gmail API, Calendar API, Vercel KV, Vercel Cron

**Architecture:**
- 3-phase cron pipeline: (1) new email processing, (2) confirmation detection, (3) user approval → calendar event
- Gmail labels track lifecycle: AutoScheduler → PendingBook → Booked
- 3 Claude calls: classify email, draft reply, detect confirmed meeting

**Key setup requirements:**
- Google Cloud project with Gmail + Calendar APIs
- OAuth scopes: gmail.readonly, gmail.modify, gmail.compose, calendar.events, calendar.readonly
- Anthropic API key
- Vercel account + KV store

**Files to build:**
- app/api/cron/route.ts (3-phase pipeline)
- lib/auth.ts (OAuth token management with KV)
- lib/gmail.ts (fetch, classify, draft, labels)
- lib/calendar.ts (FreeBusy, events, creation)
- lib/claude.ts (classify, draft, detect)
- vercel.json (cron schedule: */5 * * * *)

**Critical gotchas:**
- All 5 OAuth scopes required (calendar.readonly needed for FreeBusy even with calendar.events)
- Use newer_than:1d NOT is:unread in Gmail query
- Only apply AutoScheduler label AFTER draft succeeds
- HTML-only emails need fallback tag stripping
- Use access_type: "offline" + prompt: "consent" for refresh token

**Revisit if:** Gmail scheduling becomes a pain point, or want to give Christian/Hannah an advanced project after they finish Parts 1-3.


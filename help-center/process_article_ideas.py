#!/usr/bin/env python3
"""
Help Center Article Pipeline Processor

Workflow: Slack submission → inbox/ → drafts/ → review/ → approved/ → published/

Each article is a markdown file with YAML frontmatter that moves through folders.
"""

import os
import re
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Google Drive sync (optional - graceful degradation if not available)
try:
    from google_drive_sync import upload_draft_to_drive, add_to_pipeline_sheet
    DRIVE_SYNC_ENABLED = True
except ImportError:
    DRIVE_SYNC_ENABLED = False
    print("Note: Google Drive sync not available")

# Config
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN', '***REDACTED***')
CHANNEL_ID = "C0AFK5PHE5Q"  # #help-center-ideas
PROCESSED_EMOJI = "memo"  # Mark processed submissions

# Folder paths
BASE_DIR = Path(__file__).parent
INBOX_DIR = BASE_DIR / "inbox"
DRAFTS_DIR = BASE_DIR / "drafts"
REVIEW_DIR = BASE_DIR / "review"
APPROVED_DIR = BASE_DIR / "approved"
PUBLISHED_DIR = BASE_DIR / "published"

# Ensure folders exist
for folder in [INBOX_DIR, DRAFTS_DIR, REVIEW_DIR, APPROVED_DIR, PUBLISHED_DIR]:
    folder.mkdir(exist_ok=True)

# Topic areas for classification
TOPIC_AREAS = [
    "Product - VMP",
    "Product - SalesHub",
    "Product - TrueTour",
    "Onboarding",
    "Billing & Account",
    "Integrations",
    "Authentication & Access",
    "Domain & URLs",
    "General"
]

# Domain strategy - correct URLs
DOMAIN_URLS = {
    "platform_login": "visitingmedia.com/app/signin",
    "public_tours": "truetour.app",
    "shortlinks": "visitme.co",
    "auth_service": "auth.visitingmedia.com",
    "legacy_content": "truetour.app/legacy/",
}

client = WebClient(token=SLACK_BOT_TOKEN)


def generate_article_id(text, timestamp):
    """Generate unique article ID from content hash."""
    content = f"{text}{timestamp}"
    return hashlib.md5(content.encode()).hexdigest()[:8]


def slugify(text):
    """Convert text to filename-safe slug."""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    return text[:50].strip('-')


def get_recent_messages(hours=12):
    """Get recent messages from #help-center-ideas."""
    try:
        oldest = (datetime.now() - timedelta(hours=hours)).timestamp()
        result = client.conversations_history(
            channel=CHANNEL_ID,
            oldest=str(oldest),
            limit=50
        )
        return result.get('messages', [])
    except SlackApiError as e:
        print(f"Error fetching messages: {e}")
        return []


def is_already_processed(message):
    """Check if message has memo emoji (already processed)."""
    reactions = message.get('reactions', [])
    for reaction in reactions:
        if reaction.get('name') == PROCESSED_EMOJI:
            return True
    return False


def article_exists(article_id):
    """Check if article already exists in any folder."""
    for folder in [INBOX_DIR, DRAFTS_DIR, REVIEW_DIR, APPROVED_DIR, PUBLISHED_DIR]:
        for f in folder.glob(f"{article_id}-*.md"):
            return True
    return False


def is_submission(message):
    """Check if message looks like an article submission."""
    if message.get('bot_id'):
        return False
    if message.get('subtype') in ['channel_join', 'channel_leave', 'channel_topic', 'channel_purpose']:
        return False
    text = message.get('text', '')
    if 'has joined the channel' in text or 'has left the channel' in text:
        return False
    if message.get('thread_ts') and message.get('thread_ts') != message.get('ts'):
        return False
    if len(text) < 20:
        return False
    return True


def extract_submission_info(message):
    """Extract key information from a submission."""
    text = message.get('text', '')
    user = message.get('user', 'Unknown')

    info = {
        'raw_text': text,
        'submitter': user,
        'title': None,
        'topic_area': 'General',
        'audience': 'End customers',
        'problem': None,
        'priority': 'Medium',
        'slack_ts': message.get('ts'),
    }

    # Look for structured form fields
    title_match = re.search(r'(?:Title|Article)[:\s]*([^\n]+)', text, re.I)
    if title_match:
        info['title'] = title_match.group(1).strip()

    topic_match = re.search(r'(?:Topic|Area|Category)[:\s]*([^\n]+)', text, re.I)
    if topic_match:
        topic = topic_match.group(1).strip()
        for known_topic in TOPIC_AREAS:
            if known_topic.lower() in topic.lower():
                info['topic_area'] = known_topic
                break

    audience_match = re.search(r'(?:Audience|For)[:\s]*([^\n]+)', text, re.I)
    if audience_match:
        info['audience'] = audience_match.group(1).strip()

    problem_match = re.search(r'(?:Problem|Question|Issue|About)[:\s]*([^\n]+)', text, re.I)
    if problem_match:
        info['problem'] = problem_match.group(1).strip()

    priority_match = re.search(r'(?:Priority)[:\s]*(High|Medium|Low)', text, re.I)
    if priority_match:
        info['priority'] = priority_match.group(1).capitalize()

    # Generate title if not provided
    if not info['title']:
        first_line = text.split('\n')[0][:60]
        info['title'] = first_line + ('...' if len(text.split('\n')[0]) > 60 else '')

    return info


def needs_clarification(info):
    """Check if submission needs more info."""
    if len(info['raw_text']) < 50 and not info['problem']:
        return True, "Could you provide more detail about what this article should cover? What problem or question should it address?"
    return False, None


def save_to_inbox(article_id, info):
    """Save submission to inbox folder."""
    slug = slugify(info['title'])
    filename = f"{article_id}-{slug}.md"
    filepath = INBOX_DIR / filename

    content = f"""---
id: {article_id}
title: "{info['title']}"
submitter: {info['submitter']}
submitted: {datetime.now().isoformat()}
status: inbox
topic: {info['topic_area']}
audience: {info['audience']}
priority: {info['priority']}
slack_ts: {info['slack_ts']}
slack_channel: {CHANNEL_ID}
---

# Submission

{info['raw_text']}
"""

    filepath.write_text(content)
    print(f"  → Saved to inbox: {filename}")
    return filepath


def generate_draft(info):
    """Generate an article draft based on submission info."""
    title = info['title']
    topic = info['topic_area']
    audience = info['audience']
    problem = info['problem'] or info['raw_text']

    draft = f"""## Summary
[DRAFT - Needs SME Review]

This article explains {problem[:100]}{'...' if len(problem) > 100 else ''}.

**Topic Area:** {topic}
**Target Audience:** {audience}

---

## Overview

[Write 2-3 sentences introducing the topic and why it matters to the reader.]

[VERIFY: Confirm this accurately describes the feature/process]

## Steps / Instructions

### Step 1: [Action]

[Description of what to do]

[SCREENSHOT: Description of what screen/UI to capture]

### Step 2: [Action]

[Description of what to do]

### Step 3: [Action]

[Description of what to do]

## Important Notes

- **Platform Login URL:** {DOMAIN_URLS['platform_login']}
- **Public Tours:** {DOMAIN_URLS['public_tours']}

[VERIFY: Confirm all URLs are correct for this context]

## FAQ / Troubleshooting

**Q: [Common question]?**
A: [Answer]

**Q: [Common question]?**
A: [Answer]

## Related Articles

- [Related Article 1 - placeholder]
- [Related Article 2 - placeholder]

---

*Draft generated from submission by <@{info['submitter']}>*
*Needs SME review before publishing*
"""
    return draft


def save_to_drafts(article_id, info, draft_content):
    """Move article from inbox to drafts with generated content."""
    slug = slugify(info['title'])
    filename = f"{article_id}-{slug}.md"

    # Remove from inbox if exists
    inbox_file = INBOX_DIR / filename
    if inbox_file.exists():
        inbox_file.unlink()

    filepath = DRAFTS_DIR / filename

    content = f"""---
id: {article_id}
title: "{info['title']}"
submitter: {info['submitter']}
submitted: {datetime.now().isoformat()}
drafted: {datetime.now().isoformat()}
status: draft
topic: {info['topic_area']}
audience: {info['audience']}
priority: {info['priority']}
slack_ts: {info['slack_ts']}
slack_channel: {CHANNEL_ID}
---

# {info['title']}

{draft_content}

---

## Original Submission

{info['raw_text']}
"""

    filepath.write_text(content)
    print(f"  → Saved draft: {filename}")

    # Sync to Google Drive and tracking sheet
    if DRIVE_SYNC_ENABLED:
        try:
            # Upload to Drive "0 - Drafts" folder
            drive_file_id = upload_draft_to_drive(str(filepath), article_id, info['title'])

            # Add to tracking spreadsheet
            add_to_pipeline_sheet(
                article_id=article_id,
                title=info['title'],
                submitter=info['submitter'],
                topic=info['topic_area'],
                priority=info['priority'],
                slack_ts=info['slack_ts']
            )
        except Exception as e:
            print(f"  → Drive sync error (draft saved locally): {e}")

    return filepath


def post_draft_reply(message_ts, draft, article_id):
    """Post the draft as a thread reply."""
    try:
        intro = f"📝 *Draft Generated* (ID: `{article_id}`)\n\nHere's an initial article draft based on your submission. Please review and flag anything that needs adjusting before SME review.\n\n---\n\n"

        client.chat_postMessage(
            channel=CHANNEL_ID,
            thread_ts=message_ts,
            text=intro + draft
        )
        return True
    except SlackApiError as e:
        print(f"Error posting reply: {e}")
        return False


def post_clarification_request(message_ts, question):
    """Ask submitter for more info."""
    try:
        client.chat_postMessage(
            channel=CHANNEL_ID,
            thread_ts=message_ts,
            text=f"👋 Thanks for the submission! Before I can generate a draft, I need a bit more info:\n\n{question}"
        )
        return True
    except SlackApiError as e:
        print(f"Error posting clarification: {e}")
        return False


def mark_as_processed(message_ts):
    """Add memo emoji to mark as processed."""
    try:
        client.reactions_add(
            channel=CHANNEL_ID,
            timestamp=message_ts,
            name=PROCESSED_EMOJI
        )
    except SlackApiError as e:
        error = str(e)
        if 'already_reacted' not in error and 'missing_scope' not in error:
            print(f"Error adding reaction: {e}")


def post_summary(processed, drafts_created, needs_info):
    """Post processing summary to channel."""
    try:
        summary = f"📊 *Pipeline Update*\n\nProcessed {processed} new submission(s):\n• {drafts_created} draft(s) created\n• {needs_info} need more info\n\nView pipeline: `~/projects/support-memory/help-center/`"

        client.chat_postMessage(
            channel=CHANNEL_ID,
            text=summary
        )
    except SlackApiError as e:
        print(f"Error posting summary: {e}")


def get_pipeline_status():
    """Get current pipeline status."""
    status = {
        'inbox': len(list(INBOX_DIR.glob('*.md'))),
        'drafts': len(list(DRAFTS_DIR.glob('*.md'))),
        'review': len(list(REVIEW_DIR.glob('*.md'))),
        'approved': len(list(APPROVED_DIR.glob('*.md'))),
        'published': len(list(PUBLISHED_DIR.glob('*.md'))),
    }
    return status


def process_submissions():
    """Main processing function."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Checking #help-center-ideas...")

    # Show current pipeline status
    status = get_pipeline_status()
    print(f"Pipeline: inbox={status['inbox']} | drafts={status['drafts']} | review={status['review']} | approved={status['approved']} | published={status['published']}")

    messages = get_recent_messages(hours=12)
    print(f"Found {len(messages)} messages in last 12 hours")

    processed = 0
    drafts_created = 0
    needs_info = 0

    for msg in messages:
        if is_already_processed(msg):
            continue
        if not is_submission(msg):
            continue

        msg_ts = msg.get('ts')
        text = msg.get('text', '')

        # Generate article ID
        article_id = generate_article_id(text, msg_ts)

        # Skip if already processed (file exists)
        if article_exists(article_id):
            continue

        print(f"Processing submission: {text[:50]}...")

        info = extract_submission_info(msg)
        needs_clarify, question = needs_clarification(info)

        if needs_clarify:
            save_to_inbox(article_id, info)  # Save raw submission
            post_clarification_request(msg_ts, question)
            needs_info += 1
        else:
            # Generate draft and save to drafts folder
            draft = generate_draft(info)
            save_to_drafts(article_id, info, draft)
            if post_draft_reply(msg_ts, draft, article_id):
                drafts_created += 1

        mark_as_processed(msg_ts)
        processed += 1

    if processed > 0:
        post_summary(processed, drafts_created, needs_info)
    else:
        print("No new submissions to process")

    print(f"Done. Processed: {processed}, Drafts: {drafts_created}, Needs info: {needs_info}")


def move_article(article_id, to_folder):
    """Move an article to a different stage folder."""
    target_dir = {
        'inbox': INBOX_DIR,
        'drafts': DRAFTS_DIR,
        'review': REVIEW_DIR,
        'approved': APPROVED_DIR,
        'published': PUBLISHED_DIR,
    }.get(to_folder)

    if not target_dir:
        print(f"Unknown folder: {to_folder}")
        return False

    # Find the article
    for folder in [INBOX_DIR, DRAFTS_DIR, REVIEW_DIR, APPROVED_DIR, PUBLISHED_DIR]:
        for f in folder.glob(f"{article_id}-*.md"):
            # Read content
            content = f.read_text()

            # Update status in frontmatter
            content = re.sub(r'status: \w+', f'status: {to_folder}', content)

            # Add timestamp for this stage
            now = datetime.now().isoformat()
            if f'moved_to_{to_folder}:' not in content:
                content = content.replace('---\n\n', f'moved_to_{to_folder}: {now}\n---\n\n', 1)

            # Move file
            new_path = target_dir / f.name
            new_path.write_text(content)
            f.unlink()

            print(f"Moved {f.name} to {to_folder}/")
            return True

    print(f"Article {article_id} not found")
    return False


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == 'status':
            status = get_pipeline_status()
            print("\nArticle Pipeline Status:")
            print(f"  inbox/    : {status['inbox']} articles")
            print(f"  drafts/   : {status['drafts']} articles")
            print(f"  review/   : {status['review']} articles")
            print(f"  approved/ : {status['approved']} articles")
            print(f"  published/: {status['published']} articles")

        elif cmd == 'move' and len(sys.argv) >= 4:
            article_id = sys.argv[2]
            to_folder = sys.argv[3]
            move_article(article_id, to_folder)

        elif cmd == 'list':
            folder = sys.argv[2] if len(sys.argv) > 2 else 'drafts'
            target = {
                'inbox': INBOX_DIR,
                'drafts': DRAFTS_DIR,
                'review': REVIEW_DIR,
                'approved': APPROVED_DIR,
                'published': PUBLISHED_DIR,
            }.get(folder, DRAFTS_DIR)

            print(f"\nArticles in {folder}/:")
            for f in sorted(target.glob('*.md')):
                print(f"  {f.name}")
        else:
            print("Usage:")
            print("  python3 process_article_ideas.py          # Process new submissions")
            print("  python3 process_article_ideas.py status   # Show pipeline status")
            print("  python3 process_article_ideas.py list [folder]  # List articles in folder")
            print("  python3 process_article_ideas.py move <id> <folder>  # Move article")
    else:
        process_submissions()

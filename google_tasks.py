#!/usr/bin/env python3
"""
Google Tasks integration for Support Memory.
Read task lists and tasks for morning briefing.
"""

from datetime import datetime
from googleapiclient.discovery import build
from google_auth import get_credentials


def get_tasks_service():
    """Get authenticated Tasks API service."""
    creds = get_credentials()
    if not creds:
        return None
    return build('tasks', 'v1', credentials=creds)


def get_task_lists():
    """Get all task lists."""
    service = get_tasks_service()
    if not service:
        return []

    try:
        result = service.tasklists().list().execute()
        task_lists = result.get('items', [])
        return [{'id': tl['id'], 'title': tl['title']} for tl in task_lists]

    except Exception as e:
        print(f"Error fetching task lists: {e}")
        return []


def get_tasks(list_id='@default', show_completed=False):
    """Get tasks from a specific list."""
    service = get_tasks_service()
    if not service:
        return []

    try:
        result = service.tasks().list(
            tasklist=list_id,
            showCompleted=show_completed,
            showHidden=False
        ).execute()

        tasks = result.get('items', [])
        return [_format_task(t) for t in tasks]

    except Exception as e:
        print(f"Error fetching tasks: {e}")
        return []


def get_all_open_tasks():
    """Get all incomplete tasks across all lists."""
    task_lists = get_task_lists()
    all_tasks = []

    for tl in task_lists:
        tasks = get_tasks(tl['id'], show_completed=False)
        for task in tasks:
            task['list_name'] = tl['title']
        all_tasks.extend(tasks)

    # Sort by due date (tasks without due date go to end)
    all_tasks.sort(key=lambda t: t['due'] if t['due'] else '9999-99-99')

    return all_tasks


def create_task(title, notes=None, due_date=None, list_id='@default'):
    """Create a new task in Google Tasks.

    Args:
        title: Task title
        notes: Optional task notes/description
        due_date: Optional due date (YYYY-MM-DD string or datetime)
        list_id: Task list ID (defaults to primary list)

    Returns:
        Created task dict or None on error
    """
    service = get_tasks_service()
    if not service:
        return None

    task_body = {'title': title}

    if notes:
        task_body['notes'] = notes

    if due_date:
        if isinstance(due_date, str):
            # Assume YYYY-MM-DD format
            task_body['due'] = f"{due_date}T00:00:00.000Z"
        else:
            task_body['due'] = due_date.strftime('%Y-%m-%dT00:00:00.000Z')

    try:
        result = service.tasks().insert(tasklist=list_id, body=task_body).execute()
        print(f"  Created task: {title}")
        return _format_task(result)
    except Exception as e:
        print(f"Error creating task: {e}")
        return None


def complete_task(task_id, list_id='@default'):
    """Mark a task as completed.

    Args:
        task_id: The task ID to complete
        list_id: Task list ID (defaults to primary list)

    Returns:
        Updated task dict or None on error
    """
    service = get_tasks_service()
    if not service:
        return None

    try:
        # Get the task first
        task = service.tasks().get(tasklist=list_id, task=task_id).execute()
        # Update status to completed
        task['status'] = 'completed'
        result = service.tasks().update(tasklist=list_id, task=task_id, body=task).execute()
        print(f"  Completed task: {task.get('title', task_id)}")
        return _format_task(result)
    except Exception as e:
        print(f"Error completing task: {e}")
        return None


def find_task_by_title(search_text):
    """Find a task by partial title match.

    Args:
        search_text: Text to search for in task titles

    Returns:
        Tuple of (task, list_id) or (None, None) if not found
    """
    search_lower = search_text.lower()
    task_lists = get_task_lists()

    for tl in task_lists:
        tasks = get_tasks(tl['id'], show_completed=False)
        for task in tasks:
            if search_lower in task['title'].lower():
                return task, tl['id']

    return None, None


def complete_task_by_title(search_text):
    """Find and complete a task by partial title match.

    Args:
        search_text: Text to search for in task titles

    Returns:
        Completed task dict or None if not found
    """
    task, list_id = find_task_by_title(search_text)
    if task:
        return complete_task(task['id'], list_id)
    return None


def categorize_tasks(tasks):
    """Categorize tasks into actionable, links/learning, and reference.

    Returns dict with keys: 'actionable', 'learning', 'reference'
    """
    categorized = {
        'actionable': [],  # Real work tasks
        'learning': [],    # Links to learn/read
        'reference': [],   # Notes/reminders
    }

    for task in tasks:
        title_lower = task['title'].lower()

        # Check if it's a learning/link task
        if any(x in title_lower for x in ['http://', 'https://', 'learn', 'read', 'watch', 'explore']):
            categorized['learning'].append(task)
        # Check if it's a short reference/category task (likely a header)
        elif len(task['title']) < 15 and not task.get('due'):
            categorized['reference'].append(task)
        else:
            categorized['actionable'].append(task)

    return categorized


def get_tasks_hierarchical(list_id='@default'):
    """Get tasks with hierarchy preserved, returning categories and their subtasks.

    Returns list of category dicts: [{'name': 'CX', 'tasks': [...], 'id': '...'}, ...]
    """
    service = get_tasks_service()
    if not service:
        return []

    try:
        # Fetch all tasks with pagination (default maxResults is 20, we need all)
        raw_tasks = []
        page_token = None
        while True:
            kwargs = dict(
                tasklist=list_id,
                showCompleted=False,
                showHidden=False,
                maxResults=100,
            )
            if page_token:
                kwargs['pageToken'] = page_token
            result = service.tasks().list(**kwargs).execute()
            raw_tasks.extend(result.get('items', []))
            page_token = result.get('nextPageToken')
            if not page_token:
                break

        # Build a map of task ID -> task
        task_map = {t['id']: _format_task(t) for t in raw_tasks}

        # Find top-level tasks (no parent) - these are categories
        categories = []
        subtask_ids = set()

        for task in raw_tasks:
            formatted = task_map[task['id']]
            if formatted['parent']:
                subtask_ids.add(task['id'])

        # Sort raw_tasks by position to honour user-defined order
        raw_tasks.sort(key=lambda t: t.get('position', ''))

        # Build categories with their subtasks, preserving position order
        for task in raw_tasks:
            formatted = task_map[task['id']]
            if task['id'] not in subtask_ids:
                # This is a top-level task (category)
                cat = {
                    'name': formatted['title'],
                    'id': task['id'],
                    'position': task.get('position', ''),
                    'tasks': []
                }
                # Find all direct children, preserving their position order
                children = [
                    task_map[t['id']] for t in raw_tasks
                    if t.get('parent') == task['id']
                ]
                cat['tasks'] = children
                categories.append(cat)

        return categories

    except Exception as e:
        print(f"Error fetching hierarchical tasks: {e}")
        return []


def get_all_tasks_by_category():
    """Get all tasks organized by their parent category across all lists.

    Returns dict: {'CX': [task1, task2], 'Support': [task3, ...], ...}
    """
    task_lists = get_task_lists()
    all_categories = {}
    uncategorized = []

    for tl in task_lists:
        categories = get_tasks_hierarchical(tl['id'])
        for cat in categories:
            if cat['tasks']:
                # This category has subtasks
                if cat['name'] not in all_categories:
                    all_categories[cat['name']] = []
                all_categories[cat['name']].extend(cat['tasks'])
            else:
                # This is a standalone task (no children)
                uncategorized.append({
                    'title': cat['name'],
                    'id': cat['id'],
                    'list_name': tl['title'],
                    'due': '',
                    'notes': '',
                    'status': '',
                    'parent': None,
                })

    if uncategorized:
        all_categories['Uncategorized'] = uncategorized

    return all_categories


def _format_task(task):
    """Format a task for internal use."""
    due = task.get('due', '')
    if due:
        # Due dates come as RFC 3339 (e.g., '2024-01-15T00:00:00.000Z')
        try:
            dt = datetime.fromisoformat(due.replace('Z', '+00:00'))
            due = dt.strftime('%Y-%m-%d')
        except ValueError:
            pass  # Keep original string if parsing fails

    return {
        'id': task.get('id'),
        'title': task.get('title', 'Untitled'),
        'due': due,
        'notes': task.get('notes', ''),
        'status': task.get('status', ''),
        'parent': task.get('parent'),  # Parent task ID for hierarchy
        'position': task.get('position', ''),  # For ordering
    }


def format_for_briefing(tasks):
    """Format tasks for the morning briefing."""
    if not tasks:
        return "No open tasks."

    lines = []
    for task in tasks:
        line = f"- {task['title']}"
        if task['due']:
            line += f" (due: {task['due']})"
        if task.get('list_name'):
            line += f" [{task['list_name']}]"
        if task['notes']:
            # Add notes on next line, indented
            line += f"\n    {task['notes'][:100]}"
        lines.append(line)

    return '\n'.join(lines)


if __name__ == '__main__':
    print("=== Task Lists ===")
    lists = get_task_lists()
    if not lists:
        print("No task lists found (or not authenticated)")
    else:
        for tl in lists:
            print(f"  - {tl['title']} ({tl['id']})")

    print("\n=== All Open Tasks ===")
    tasks = get_all_open_tasks()
    if not tasks:
        print("No open tasks")
    else:
        print(format_for_briefing(tasks))

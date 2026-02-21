#!/usr/bin/env python3
"""
Helm Dashboard
Lucas's personal operational memory — context layer on top of Google Tasks.
Google Tasks is the source of truth — manage tasks there.
This shows everything together: tasks + meetings + decisions + capture.

Run: python3 dashboard.py
Open: http://localhost:5010
"""

import os
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request

try:
    from google_tasks import get_all_tasks_by_category, create_task
    TASKS_AVAILABLE = True
except Exception:
    TASKS_AVAILABLE = False

try:
    from shared_memory import load_memory
    MEMORY_AVAILABLE = True
except Exception:
    MEMORY_AVAILABLE = False

try:
    from google_calendar import get_todays_events, get_upcoming_events
    CALENDAR_AVAILABLE = True
except Exception:
    CALENDAR_AVAILABLE = False

app = Flask(__name__)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Helm</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0f0f13;
    color: #e2e2e8;
    min-height: 100vh;
  }

  .header {
    background: #18181f;
    border-bottom: 1px solid #2a2a35;
    padding: 14px 28px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 100;
  }

  .header-left { display: flex; align-items: center; gap: 12px; }

  .logo { font-size: 26px; font-weight: 700; color: #7c6af7; letter-spacing: -0.5px; }

  .date-badge {
    font-size: 14px;
    font-weight: 500;
    color: #9090a8;
    letter-spacing: 0.1px;
  }

  .header-right { display: flex; align-items: center; gap: 10px; }

  .gtasks-btn {
    background: #4285f4;
    color: white;
    border: none;
    padding: 7px 14px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .gtasks-btn:hover { background: #3367d6; }
  .gtasks-btn.support { background: #0f766e; }
  .gtasks-btn.support:hover { background: #0d6560; }

  .refresh-btn {
    background: #22222c;
    border: 1px solid #2a2a35;
    color: #888;
    padding: 7px 14px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
  }
  .refresh-btn:hover { background: #2a2a35; color: #ccc; }

  .layout {
    display: grid;
    grid-template-columns: 1fr 360px;
    gap: 20px;
    padding: 20px 28px;
    max-width: 1300px;
    margin: 0 auto;
  }

  .main-col { display: flex; flex-direction: column; gap: 18px; }
  .side-col { display: flex; flex-direction: column; gap: 18px; }

  .card {
    background: #18181f;
    border: 1px solid #2a2a35;
    border-radius: 10px;
    overflow: hidden;
  }

  .card-header {
    padding: 12px 16px;
    border-bottom: 1px solid #2a2a35;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .card-title {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: #666;
  }

  .card-count {
    font-size: 12px;
    background: #22222c;
    color: #888;
    padding: 2px 8px;
    border-radius: 10px;
  }

  /* Stats */
  .stats-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
  }

  .stat-card {
    background: #18181f;
    border: 1px solid #2a2a35;
    border-radius: 10px;
    padding: 16px;
    text-align: center;
  }

  .stat-number {
    font-size: 32px;
    font-weight: 700;
    color: #7c6af7;
    line-height: 1;
  }

  .stat-label {
    font-size: 12px;
    color: #555;
    margin-top: 5px;
  }

  /* Tasks — read only */
  .category-block { border-bottom: 1px solid #1e1e28; }
  .category-block:last-child { border-bottom: none; }

  .category-label {
    padding: 8px 16px;
    background: #1c1c24;
    font-size: 11px;
    font-weight: 600;
    color: #7c6af7;
    letter-spacing: 0.4px;
    display: flex;
    justify-content: space-between;
  }

  .task-row {
    padding: 9px 16px;
    border-bottom: 1px solid #1a1a22;
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .task-row:last-child { border-bottom: none; }

  .task-dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: #3a3a50;
    flex-shrink: 0;
    margin-top: 6px;
  }

  .task-text { font-size: 14px; color: #c8c8d8; line-height: 1.4; flex: 1; }
  .task-due { font-size: 12px; flex-shrink: 0; }
  .due-overdue { color: #ef4444; }
  .due-today { color: #f59e0b; }
  .due-soon { color: #6b7280; }

  .subgroup { background: #16161e; }
  .subgroup-label {
    padding: 6px 16px 6px 24px;
    font-size: 11px;
    font-weight: 600;
    color: #555;
    letter-spacing: 0.3px;
    border-bottom: 1px solid #1a1a22;
  }
  .task-row-indent { padding-left: 28px; }

  .manage-tasks-hint {
    padding: 10px 16px;
    font-size: 12px;
    color: #3a3a50;
    text-align: center;
    border-top: 1px solid #1e1e28;
  }

  /* Projects collapsible section */
  .projects-toggle {
    padding: 10px 16px;
    background: #14141c;
    border-top: 1px solid #1e1e28;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: space-between;
    user-select: none;
  }
  .projects-toggle:hover { background: #1a1a24; }
  .projects-toggle-label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: #444;
  }
  .projects-toggle-arrow { font-size: 11px; color: #444; transition: transform 0.2s; }
  .projects-toggle-arrow.open { transform: rotate(180deg); }
  .projects-body { display: none; }
  .projects-body.open { display: block; }
  .projects-list-label {
    padding: 7px 16px;
    background: #111118;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: #333;
    border-bottom: 1px solid #1a1a22;
    border-top: 1px solid #1a1a22;
  }

  /* Meetings */
  .meeting-row {
    padding: 12px 16px;
    border-bottom: 1px solid #1a1a22;
  }
  .meeting-row:last-child { border-bottom: none; }

  .meeting-name {
    font-size: 14px;
    font-weight: 500;
    color: #d4d4e0;
    margin-bottom: 3px;
  }

  .meeting-date { font-size: 12px; color: #555; margin-bottom: 7px; }

  .action-line {
    font-size: 13px;
    color: #9090a8;
    padding: 3px 0 3px 12px;
    border-left: 2px solid #2a2a45;
    margin-bottom: 3px;
    line-height: 1.4;
  }

  /* Calendar / Meetings */
  .cal-day-header {
    padding: 7px 16px;
    background: #1c1c24;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: #7c6af7;
    border-bottom: 1px solid #1e1e28;
  }
  .cal-day-header.today { color: #7c6af7; }
  .cal-day-header.future { color: #444; }

  .cal-event {
    padding: 10px 16px;
    border-bottom: 1px solid #1a1a22;
    display: flex;
    gap: 12px;
    align-items: flex-start;
  }
  .cal-event:last-child { border-bottom: none; }

  .cal-time {
    font-size: 12px;
    color: #555;
    width: 70px;
    flex-shrink: 0;
    padding-top: 1px;
    font-variant-numeric: tabular-nums;
  }

  .cal-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
    margin-top: 4px;
  }

  .cal-event.past .cal-dot   { background: #2a2a3a; }
  .cal-event.now  .cal-dot   { background: #4ade80; box-shadow: 0 0 6px #4ade8066; }
  .cal-event.upcoming .cal-dot { background: #7c6af7; }
  .cal-event.allday .cal-dot { background: #444; }

  .cal-body { flex: 1; min-width: 0; }

  .cal-title {
    font-size: 14px;
    line-height: 1.3;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .cal-event.past .cal-title    { color: #444; }
  .cal-event.now  .cal-title    { color: #e2e2e8; font-weight: 500; }
  .cal-event.upcoming .cal-title { color: #c8c8d8; }
  .cal-event.allday .cal-title  { color: #555; }

  .cal-meta {
    font-size: 11px;
    color: #3a3a50;
    margin-top: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .cal-event.now .cal-meta { color: #4ade8066; color: #2d6a3f; }

  .cal-link {
    color: inherit;
    text-decoration: none;
  }
  .cal-link:hover .cal-title { text-decoration: underline; }

  /* Quick capture */
  .capture-body { padding: 14px 16px; }

  .capture-input {
    width: 100%;
    background: #22222c;
    border: 1px solid #2a2a35;
    color: #e2e2e8;
    padding: 10px 12px;
    border-radius: 7px;
    font-size: 14px;
    font-family: inherit;
    resize: none;
    height: 72px;
    outline: none;
    transition: border-color 0.15s;
  }
  .capture-input:focus { border-color: #7c6af7; }
  .capture-input::placeholder { color: #3a3a50; }

  .capture-hint {
    font-size: 12px;
    color: #444;
    margin-top: 8px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .btn-add {
    background: #7c6af7;
    color: white;
    border: none;
    padding: 7px 16px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
  }
  .btn-add:hover { background: #6c5ae7; }

  /* Decisions */
  .decision-row {
    padding: 10px 16px;
    border-bottom: 1px solid #1a1a22;
  }
  .decision-row:last-child { border-bottom: none; }
  .decision-text { font-size: 13px; color: #a0a0b8; line-height: 1.4; }
  .decision-source { font-size: 11px; color: #444; margin-top: 3px; }

  .empty { padding: 20px 16px; text-align: center; color: #3a3a50; font-size: 13px; }

  /* Helm Tasks (CLAUDE.md) */
  .helm-task-row {
    padding: 8px 16px;
    border-bottom: 1px solid #1a1a22;
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .helm-task-row:last-child { border-bottom: none; }

  .helm-badge {
    font-size: 10px;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 4px;
    flex-shrink: 0;
    text-transform: uppercase;
    letter-spacing: 0.4px;
  }
  .badge-in_progress { background: #2a1f00; color: #f59e0b; }
  .badge-pending     { background: #1a1a2e; color: #7c6af7; }
  .badge-blocked     { background: #2a0000; color: #ef4444; }

  .helm-task-text { font-size: 13px; color: #b0b0c8; flex: 1; line-height: 1.4; }

  /* Meeting Prep Panel */
  .prep-btn {
    font-size: 10px;
    font-weight: 600;
    color: #7c6af7;
    background: #1e1a3a;
    border: none;
    border-radius: 4px;
    padding: 2px 7px;
    cursor: pointer;
    flex-shrink: 0;
    margin-left: auto;
    letter-spacing: 0.3px;
    opacity: 0.8;
  }
  .prep-btn:hover { opacity: 1; background: #2a2250; }

  .prep-panel {
    position: fixed;
    top: 0; right: 0;
    width: 420px;
    height: 100vh;
    background: #18181f;
    border-left: 1px solid #2a2a35;
    z-index: 500;
    display: flex;
    flex-direction: column;
    transform: translateX(100%);
    transition: transform 0.22s ease;
    box-shadow: -8px 0 32px #00000066;
  }
  .prep-panel.open { transform: translateX(0); }

  .prep-panel-header {
    padding: 16px 18px 12px;
    border-bottom: 1px solid #2a2a35;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
  }
  .prep-panel-title {
    font-size: 14px;
    font-weight: 600;
    color: #e2e2e8;
    line-height: 1.3;
  }
  .prep-panel-sub {
    font-size: 12px;
    color: #555;
    margin-top: 3px;
  }
  .prep-close {
    background: none;
    border: none;
    color: #555;
    font-size: 20px;
    cursor: pointer;
    line-height: 1;
    padding: 0;
    flex-shrink: 0;
  }
  .prep-close:hover { color: #ccc; }

  .prep-panel-body {
    flex: 1;
    overflow-y: auto;
    padding: 16px 18px;
  }

  .prep-loading {
    color: #555;
    font-size: 13px;
    text-align: center;
    padding: 40px 0;
  }
  .prep-loading-dot {
    display: inline-block;
    animation: pulse 1.2s ease-in-out infinite;
  }
  @keyframes pulse { 0%,100%{opacity:0.3} 50%{opacity:1} }

  .prep-section {
    margin-bottom: 18px;
  }
  .prep-section-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: #444;
    margin-bottom: 8px;
  }
  .prep-brief {
    font-size: 13px;
    color: #c8c8d8;
    line-height: 1.65;
    white-space: pre-wrap;
  }
  .prep-task-item {
    font-size: 13px;
    color: #a0a0b8;
    padding: 5px 0;
    border-bottom: 1px solid #1e1e28;
    line-height: 1.4;
    display: flex;
    gap: 8px;
    align-items: baseline;
  }
  .prep-task-item:last-child { border-bottom: none; }
  .prep-task-dot { color: #3a3a50; flex-shrink: 0; }

  .prep-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: #00000044;
    z-index: 499;
  }
  .prep-overlay.open { display: block; }

  /* Weather */
  .weather-now {
    padding: 14px 16px 10px;
    display: flex;
    align-items: center;
    gap: 14px;
    border-bottom: 1px solid #1e1e28;
  }

  .weather-icon { font-size: 36px; line-height: 1; }

  .weather-temp {
    font-size: 34px;
    font-weight: 700;
    color: #e2e2e8;
    line-height: 1;
  }

  .weather-desc {
    font-size: 13px;
    color: #666;
    margin-top: 3px;
  }

  .weather-hourly {
    padding: 8px 0 4px;
  }

  .weather-hour {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 5px 16px;
    font-size: 13px;
  }

  .wh-time { color: #555; width: 48px; flex-shrink: 0; font-variant-numeric: tabular-nums; }
  .wh-icon { font-size: 15px; width: 20px; text-align: center; }
  .wh-temp { color: #c8c8d8; font-weight: 500; width: 36px; }
  .wh-rain { color: #4a9eff; font-size: 12px; margin-left: auto; }
  .wh-rain.low { color: #2a2a45; }

  .weather-hour.now-hour { background: #1c1c28; }
  .weather-hour.now-hour .wh-time { color: #7c6af7; font-weight: 600; }

  .toast {
    position: fixed;
    bottom: 20px;
    right: 20px;
    background: #7c6af7;
    color: white;
    padding: 10px 18px;
    border-radius: 7px;
    font-size: 13px;
    font-weight: 500;
    opacity: 0;
    transform: translateY(8px);
    transition: all 0.18s;
    z-index: 1000;
  }
  .toast.show { opacity: 1; transform: translateY(0); }
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <div class="logo">☸ Helm</div>
    <div class="date-badge" id="current-date"></div>
  </div>
  <div class="header-right">
    <a class="gtasks-btn support" href="https://visitingmedia.zendesk.com/explore/studio#/dashboards/precanned/9425F76AF99EC760E6FDE83C5A99EE472407CBD6B0D5A3DA700AB5DDE040C541" target="_blank">
      ◎ Support Dashboard
    </a>
    <a class="gtasks-btn" href="https://lucaswillett.github.io/ai-in-action/" target="_blank" style="background:#6366f1">
      ⚡ AI in Action
    </a>
    <a class="gtasks-btn" href="https://tasks.google.com" target="_blank">
      ✓ Google Tasks
    </a>
    <button class="refresh-btn" onclick="loadAll()">↻</button>
  </div>
</div>

<div class="layout">
  <div class="main-col">

    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-number" id="stat-tasks">—</div>
        <div class="stat-label">My Tasks</div>
      </div>
      <div class="stat-card">
        <div class="stat-number" id="stat-total">—</div>
        <div class="stat-label">Open Items</div>
      </div>
      <div class="stat-card">
        <div class="stat-number" id="stat-meetings">—</div>
        <div class="stat-label">Meetings Today</div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <span class="card-title">Tasks</span>
        <span class="card-count" id="task-count">—</span>
      </div>
      <div id="tasks-container"><div class="empty">Loading...</div></div>
      <div class="manage-tasks-hint">Reorder, indent &amp; complete in Google Tasks →</div>
    </div>

    <div class="card">
      <div class="card-header">
        <span class="card-title">Meetings</span>
        <span class="card-count" id="meeting-count">—</span>
      </div>
      <div id="meetings-container"><div class="empty">Loading...</div></div>
    </div>

  </div>
  <div class="side-col">

    <div class="card">
      <div class="card-header">
        <span class="card-title" style="color:#f59e0b">⚓ Helm Tasks</span>
        <span style="font-size:11px;color:#444">from CLAUDE.md</span>
      </div>
      <div id="anchor-tasks-container"><div class="empty">Loading...</div></div>
    </div>

    <div class="card">
      <div class="card-header">
        <span class="card-title">Quick Capture</span>
      </div>
      <div class="capture-body">
        <textarea
          class="capture-input"
          id="capture-input"
          placeholder="Add a task... it goes straight to Google Tasks"
        ></textarea>
        <div class="capture-hint">
          <span>Enter to add · Shift+Enter for new line</span>
          <button class="btn-add" onclick="submitCapture()">Add</button>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <span class="card-title">Weather · West Linn</span>
        <span style="font-size:11px;color:#444" id="weather-updated"></span>
      </div>
      <div id="weather-container"><div class="empty">Loading...</div></div>
    </div>

    <div class="card">
      <div class="card-header">
        <span class="card-title">Recent Decisions</span>
      </div>
      <div id="decisions-container"><div class="empty">Loading...</div></div>
    </div>

  </div>
</div>

<div class="toast" id="toast"></div>

<div class="prep-overlay" id="prep-overlay" onclick="closePrepPanel()"></div>
<div class="prep-panel" id="prep-panel">
  <div class="prep-panel-header">
    <div>
      <div class="prep-panel-title" id="prep-panel-title">Meeting Prep</div>
      <div class="prep-panel-sub" id="prep-panel-sub"></div>
    </div>
    <button class="prep-close" onclick="closePrepPanel()">✕</button>
  </div>
  <div class="prep-panel-body" id="prep-panel-body">
    <div class="prep-loading">Loading brief...</div>
  </div>
</div>

<script>
function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2200);
}

function setDate() {
  const now = new Date();
  document.getElementById('current-date').textContent =
    now.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
}

function renderGroups(groups, indent) {
  let html = '';
  const pad = indent ? 'task-row-indent' : '';
  for (const g of groups) {
    if (g.type === 'group') {
      html += `<div class="subgroup"><div class="subgroup-label">${g.name}</div>`;
      for (const t of g.tasks) {
        const dueClass = t.due_today ? 'due-today' : t.due_soon ? 'due-soon' : '';
        const due = t.due_display ? `<span class="task-due ${dueClass}">${t.due_display}</span>` : '';
        html += `<div class="task-row task-row-indent"><div class="task-dot"></div><div class="task-text">${t.title}</div>${due}</div>`;
      }
      html += '</div>';
    } else {
      const dueClass = g.due_today ? 'due-today' : g.due_soon ? 'due-soon' : '';
      const due = g.due_display ? `<span class="task-due ${dueClass}">${g.due_display}</span>` : '';
      html += `<div class="task-row ${pad}"><div class="task-dot"></div><div class="task-text">${g.title}</div>${due}</div>`;
    }
  }
  return html;
}

async function loadTasks() {
  try {
    const res = await fetch('/api/tasks');
    const data = await res.json();
    const lists = data.lists || [];

    // Split My Tasks from project lists
    const myTasksList = lists.find(l => l.name === 'My Tasks');
    const projectLists = lists.filter(l => l.name !== 'My Tasks');

    // Count My Tasks only for stat
    const myCount = myTasksList ? myTasksList.groups.reduce((n, g) => n + (g.type === 'group' ? g.tasks.length : 1), 0) : 0;
    document.getElementById('stat-tasks').textContent = myCount;
    document.getElementById('stat-total').textContent = data.total || 0;
    document.getElementById('task-count').textContent = data.total || 0;

    const container = document.getElementById('tasks-container');
    if (!lists.length) { container.innerHTML = '<div class="empty">No open tasks</div>'; return; }

    let html = '';

    // My Tasks — prominent, no list header
    if (myTasksList) {
      html += renderGroups(myTasksList.groups, false);
    }

    // Project lists — collapsible
    if (projectLists.length) {
      const totalProject = projectLists.reduce((n, l) => n + l.groups.reduce((m, g) => m + (g.type === 'group' ? g.tasks.length : 1), 0), 0);
      html += `<div class="projects-toggle" onclick="toggleProjects(this)">
        <span class="projects-toggle-label">Projects &amp; Context <span style="color:#333;font-weight:400">(${totalProject})</span></span>
        <span class="projects-toggle-arrow">▾</span>
      </div>
      <div class="projects-body" id="projects-body">`;
      for (const list of projectLists) {
        html += `<div class="projects-list-label">${list.name}</div>`;
        html += renderGroups(list.groups, false);
      }
      html += '</div>';
    }

    container.innerHTML = html;
  } catch(e) {
    document.getElementById('tasks-container').innerHTML = '<div class="empty">Could not load tasks</div>';
  }
}

function toggleProjects(el) {
  const body = document.getElementById('projects-body');
  const arrow = el.querySelector('.projects-toggle-arrow');
  body.classList.toggle('open');
  arrow.classList.toggle('open');
}

async function loadMeetings() {
  try {
    const res = await fetch('/api/calendar');
    const data = await res.json();
    const days = data.days || [];
    const todayCount = data.today_count || 0;
    document.getElementById('stat-meetings').textContent = todayCount;
    document.getElementById('meeting-count').textContent = days.reduce((n, d) => n + d.events.length, 0);

    const container = document.getElementById('meetings-container');
    if (!days.length) { container.innerHTML = '<div class="empty">No meetings</div>'; return; }

    let html = '';
    for (const day of days) {
      const isToday = day.label === 'Today';
      html += `<div class="cal-day-header ${isToday ? 'today' : 'future'}">${day.label}</div>`;
      if (!day.events.length) {
        html += `<div class="cal-event allday"><div class="cal-time"></div><div class="cal-dot"></div><div class="cal-body"><div class="cal-title" style="color:#333">No meetings</div></div></div>`;
        continue;
      }
      for (const e of day.events) {
        const status = e.status || 'upcoming';
        const timeLabel = e.time === 'All day' ? 'All day' : e.time;
        const attendees = (e.attendees_display || []).slice(0, 3).join(', ');
        const metaStr = attendees || (e.end_time ? `Until ${e.end_time}` : '');
        const nowPip = status === 'now' ? ' 🟢' : '';
        const prepAttendees = encodeURIComponent(JSON.stringify(e.attendees_display || []));
        const prepTitle = encodeURIComponent(e.title);
        const prepBtn = `<button class="prep-btn" onclick="openPrepPanel(event,'${prepTitle}','${prepAttendees}','${encodeURIComponent(e.time||'')}')">Prep ▶</button>`;
        const inner = `<div class="cal-time">${timeLabel}</div>
          <div class="cal-dot"></div>
          <div class="cal-body">
            <div class="cal-title">${e.title}${nowPip}</div>
            ${metaStr ? `<div class="cal-meta">${metaStr}</div>` : ''}
          </div>
          ${status !== 'past' ? prepBtn : ''}`;
        if (e.link) {
          html += `<div class="cal-event ${status}"><a class="cal-link" href="${e.link}" target="_blank" style="display:contents">${inner}</a></div>`;
        } else {
          html += `<div class="cal-event ${status}">${inner}</div>`;
        }
      }
    }
    container.innerHTML = html;
  } catch(e) {
    document.getElementById('meetings-container').innerHTML = '<div class="empty">Could not load calendar</div>';
  }
}

async function loadAnchorTasks() {
  try {
    const res = await fetch('/api/anchor-tasks');
    const data = await res.json();
    const tasks = data.tasks || [];
    const container = document.getElementById('anchor-tasks-container');
    if (!tasks.length) { container.innerHTML = '<div class="empty">All clear</div>'; return; }

    const labels = { in_progress: 'Active', pending: 'Pending', blocked: 'Blocked' };
    let html = '';
    for (const t of tasks) {
      const label = labels[t.status] || t.status;
      html += `<div class="helm-task-row">
        <span class="helm-badge badge-${t.status}">${label}</span>
        <span class="helm-task-text">${t.title}</span>
      </div>`;
    }
    container.innerHTML = html;
  } catch(e) {
    document.getElementById('anchor-tasks-container').innerHTML = '<div class="empty">Could not load</div>';
  }
}

async function loadDecisions() {
  try {
    const res = await fetch('/api/decisions');
    const data = await res.json();
    const decisions = data.decisions || [];
    const container = document.getElementById('decisions-container');
    if (!decisions.length) { container.innerHTML = '<div class="empty">No recent decisions</div>'; return; }

    let html = '';
    for (const d of decisions.slice(0, 8)) {
      html += `<div class="decision-row">
        <div class="decision-text">${d.decision}</div>
        <div class="decision-source">${d.from}</div>
      </div>`;
    }
    container.innerHTML = html;
  } catch(e) {
    document.getElementById('decisions-container').innerHTML = '<div class="empty">No data</div>';
  }
}

async function submitCapture() {
  const input = document.getElementById('capture-input');
  const text = input.value.trim();
  if (!text) return;
  try {
    const res = await fetch('/api/capture', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    const data = await res.json();
    if (data.ok) {
      const label = data.title && data.title !== text ? `→ "${data.title}"` : '';
      showToast('Added to Google Tasks ✓ ' + label);
      input.value = '';
      setTimeout(loadTasks, 800);
    } else {
      showToast('Failed to add task');
    }
  } catch(e) {
    showToast('Error');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('capture-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitCapture(); }
  });
});

function openPrepPanel(evt, titleEnc, attendeesEnc, timeEnc) {
  evt.preventDefault(); evt.stopPropagation();
  const title = decodeURIComponent(titleEnc);
  const attendees = JSON.parse(decodeURIComponent(attendeesEnc));
  const time = decodeURIComponent(timeEnc);
  document.getElementById('prep-panel-title').textContent = title;
  document.getElementById('prep-panel-sub').textContent = attendees.length ? attendees.join(', ') : time;
  document.getElementById('prep-panel-body').innerHTML = '<div class="prep-loading"><span class="prep-loading-dot">●</span> Building your brief...</div>';
  document.getElementById('prep-panel').classList.add('open');
  document.getElementById('prep-overlay').classList.add('open');

  fetch('/api/meeting-prep', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({title, attendees, time})
  })
  .then(r => r.json())
  .then(data => {
    const body = document.getElementById('prep-panel-body');
    let html = '';
    if (data.brief) {
      html += `<div class="prep-section"><div class="prep-section-label">Brief</div><div class="prep-brief">${data.brief}</div></div>`;
    }
    if (data.tasks && data.tasks.length) {
      html += `<div class="prep-section"><div class="prep-section-label">Open Items (${data.tasks.length})</div>`;
      for (const t of data.tasks) {
        html += `<div class="prep-task-item"><span class="prep-task-dot">◦</span><span>${t}</span></div>`;
      }
      html += '</div>';
    }
    if (!html) html = '<div class="prep-loading">No context found yet — add meeting notes via Quick Capture to build history.</div>';
    body.innerHTML = html;
  })
  .catch(() => {
    document.getElementById('prep-panel-body').innerHTML = '<div class="prep-loading">Could not generate brief.</div>';
  });
}

function closePrepPanel() {
  document.getElementById('prep-panel').classList.remove('open');
  document.getElementById('prep-overlay').classList.remove('open');
}

async function loadWeather() {
  try {
    const res = await fetch('/api/weather');
    const data = await res.json();
    if (data.error) { document.getElementById('weather-container').innerHTML = '<div class="empty">Unavailable</div>'; return; }

    const now = new Date();
    const currentHour = now.getHours();

    let html = `<div class="weather-now">
      <div class="weather-icon">${data.icon}</div>
      <div>
        <div class="weather-temp">${data.temp}°</div>
        <div class="weather-desc">${data.description}</div>
      </div>
    </div><div class="weather-hourly">`;

    for (const h of data.hours) {
      const isNow = h.hour === currentHour;
      const rainClass = h.rain < 20 ? 'low' : '';
      html += `<div class="weather-hour${isNow ? ' now-hour' : ''}">
        <span class="wh-time">${isNow ? 'Now' : h.label}</span>
        <span class="wh-icon">${h.icon}</span>
        <span class="wh-temp">${h.temp}°</span>
        <span class="wh-rain ${rainClass}">${h.rain > 0 ? h.rain + '% 💧' : ''}</span>
      </div>`;
    }
    html += '</div>';
    document.getElementById('weather-container').innerHTML = html;
    document.getElementById('weather-updated').textContent = data.updated || '';
  } catch(e) {
    document.getElementById('weather-container').innerHTML = '<div class="empty">Could not load weather</div>';
  }
}

function loadAll() { setDate(); loadTasks(); loadMeetings(); loadDecisions(); loadAnchorTasks(); loadWeather(); }
loadAll();
</script>
</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(DASHBOARD_HTML)


def _format_due(due_str, today):
    if not due_str:
        return '', False, False
    try:
        due_date = datetime.fromisoformat(due_str[:10]).date()
        delta = (due_date - today).days
        if delta < 0:
            return 'Overdue', False, True
        elif delta == 0:
            return 'Today', False, True
        elif delta <= 7:
            return due_date.strftime('%b %d'), True, False
        else:
            return due_date.strftime('%b %d'), False, False
    except Exception:
        return '', False, False


def _format_task_for_display(t, today):
    due_display, due_soon, due_today = _format_due(t.get('due', ''), today)
    return {
        'title': t.get('title', ''),
        'due_display': due_display,
        'due_soon': due_soon,
        'due_today': due_today,
    }


@app.route('/api/tasks')
def api_tasks():
    if not TASKS_AVAILABLE:
        return jsonify({'lists': [], 'total': 0})
    try:
        from google_tasks import get_task_lists, get_tasks_hierarchical
        task_lists = get_task_lists()
        today = datetime.now().date()
        total = 0
        result_lists = []

        for tl in task_lists:
            raw_cats = get_tasks_hierarchical(tl['id'])
            groups = []

            for cat in raw_cats:
                if cat['tasks']:
                    # Parent task with children — show as a sub-group
                    subtasks = []
                    for t in cat['tasks']:
                        fd = _format_task_for_display(t, today)
                        subtasks.append(fd)
                        total += 1
                    groups.append({'type': 'group', 'name': cat['name'], 'tasks': subtasks})
                else:
                    # Standalone task
                    fd = _format_task_for_display({'title': cat['name'], 'due': ''}, today)
                    groups.append({'type': 'task', **fd})
                    total += 1

            if groups:
                result_lists.append({'name': tl['title'], 'groups': groups})

        return jsonify({'lists': result_lists, 'total': total})
    except Exception as e:
        return jsonify({'error': str(e), 'lists': [], 'total': 0})


@app.route('/api/calendar')
def api_calendar():
    if not CALENDAR_AVAILABLE:
        return jsonify({'days': [], 'today_count': 0})
    try:
        from datetime import timezone
        now = datetime.now().astimezone()
        today_str = now.strftime('%Y-%m-%d')

        # Google Calendar colorId reference:
        # 1=Lavender, 2=Sage, 3=Grape(purple), 4=Flamingo, 5=Banana,
        # 6=Tangerine(orange), 7=Peacock(blue), 8=Blueberry(dark blue),
        # 9=Basil, 10=Tomato(red), 11=Flamingo
        # None/default = calendar default color (usually blue for primary)
        # Keep: blue/purple (1=Lavender, 3=Grape, 7=Peacock, 8=Blueberry, None/default)
        # Skip: red/orange time blocks (6=Tangerine, 10=Tomato, 4=Flamingo, 11=Flamingo)
        SKIP_COLOR_IDS = {'4', '6', '10', '11'}  # orange, red, flamingo

        def is_real_meeting(e):
            # Empty color_id = calendar default (blue) = keep
            return str(e.get('color_id', '')) not in SKIP_COLOR_IDS

        # Today's full day (including past events) + next 4 days upcoming
        today_events = [e for e in get_todays_events() if is_real_meeting(e)]
        upcoming = [e for e in get_upcoming_events(days=5) if is_real_meeting(e)]

        # Merge: today_events covers all of today; upcoming covers from now
        # Use today_events for today, upcoming for future days
        seen_ids = {e['id'] for e in today_events}
        future_events = [e for e in upcoming if e['date'] != today_str and e['id'] not in seen_ids]

        # Compute status for each event
        def with_status(e):
            if e['time'] == 'All day' or not e.get('start_iso'):
                e['status'] = 'allday'
                return e
            try:
                start_dt = datetime.fromisoformat(e['start_iso'])
                end_dt = datetime.fromisoformat(e['end_iso']) if e.get('end_iso') else start_dt
                if end_dt < now:
                    e['status'] = 'past'
                elif start_dt <= now <= end_dt:
                    e['status'] = 'now'
                else:
                    e['status'] = 'upcoming'
            except Exception:
                e['status'] = 'upcoming'
            return e

        today_events = [with_status(e) for e in today_events]
        future_events = [with_status(e) for e in future_events]

        # Group future by date
        future_by_date = {}
        for e in future_events:
            future_by_date.setdefault(e['date'], []).append(e)

        days = [{'date': today_str, 'label': 'Today', 'events': today_events}]
        for date_key in sorted(future_by_date.keys())[:3]:
            try:
                label = datetime.fromisoformat(date_key).strftime('%A, %b %-d')
            except Exception:
                label = date_key
            days.append({'date': date_key, 'label': label, 'events': future_by_date[date_key]})

        today_count = len(today_events)
        return jsonify({'days': days, 'today_count': today_count})
    except Exception as e:
        return jsonify({'error': str(e), 'days': [], 'today_count': 0})


@app.route('/api/meetings')
def api_meetings():
    if not MEMORY_AVAILABLE:
        return jsonify({'meetings': []})
    try:
        mem = load_memory()
        meetings = list(reversed(mem.get('meetings', [])[-10:]))
        return jsonify({'meetings': meetings})
    except Exception as e:
        return jsonify({'error': str(e), 'meetings': []})


@app.route('/api/decisions')
def api_decisions():
    if not MEMORY_AVAILABLE:
        return jsonify({'decisions': []})
    try:
        mem = load_memory()
        decisions = []
        for m in reversed(mem.get('meetings', [])[-15:]):
            for d in m.get('signals', {}).get('decisions', []):
                decisions.append({'decision': d, 'from': m.get('title', ''), 'date': m.get('date', '')})
        return jsonify({'decisions': decisions[:10]})
    except Exception as e:
        return jsonify({'error': str(e), 'decisions': []})


def parse_anchor_tasks():
    """Parse the running to-do list from ~/.claude/CLAUDE.md."""
    claude_md = os.path.expanduser('~/.claude/CLAUDE.md')
    items = []
    STATUS = {
        '🔄': 'in_progress',
        '[ ]': 'pending',
        '🚧': 'blocked',
    }
    try:
        with open(claude_md) as f:
            content = f.read()
        in_todo = False
        for line in content.split('\n'):
            if '## Running To-Do List' in line:
                in_todo = True
                continue
            if in_todo and line.startswith('## '):
                break
            if not in_todo:
                continue
            stripped = line.strip()
            for marker, status in STATUS.items():
                if stripped.startswith(f'- {marker}'):
                    text = stripped[len(f'- {marker}'):].strip()
                    # Pull bold title if present
                    import re
                    m = re.match(r'\*\*(.+?)\*\*', text)
                    title = m.group(1) if m else text.split('—')[0].strip()
                    items.append({'title': title, 'status': status})
                    break
    except Exception as e:
        print(f"Could not parse CLAUDE.md: {e}")
    return items


@app.route('/api/anchor-tasks')
def api_anchor_tasks():
    return jsonify({'tasks': parse_anchor_tasks()})


def distill_to_task(raw_text):
    """Use Claude to distill raw text (DMs, notes, blobs) into a clean action item title + notes."""
    import re as _re
    if len(raw_text) < 80:
        return raw_text, None

    # Always extract URLs from raw text — they must survive regardless of Claude output
    urls = _re.findall(r'https?://[^\s\)\"\']+', raw_text)

    try:
        import anthropic, json as _json
        client = anthropic.Anthropic()
        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=300,
            messages=[{
                'role': 'user',
                'content': (
                    'Extract the action item from this message.\n'
                    'Return ONLY a JSON object, no markdown:\n'
                    '{"title": "imperative verb phrase under 70 chars", "notes": "one sentence of context. Include any relevant URLs verbatim."}\n\n'
                    f'Message:\n{raw_text[:2000]}'
                )
            }]
        )
        raw_response = response.content[0].text.strip()
        raw_response = _re.sub(r'^```json?\s*|\s*```$', '', raw_response, flags=_re.MULTILINE).strip()
        data = _json.loads(raw_response)
        title = data.get('title', '').strip()
        notes = data.get('notes', '').strip() or None
        if title:
            # Append any URLs not already in notes
            if urls:
                missing = [u for u in urls if not notes or u not in notes]
                if missing:
                    notes = (notes + '\n' if notes else '') + ' '.join(missing)
            return title, notes
    except Exception as e:
        print(f"Distill error: {e}")

    # Fallback: first line as title, full text + urls as notes
    first_line = raw_text.split('\n')[0].strip()[:100]
    notes = raw_text[:500]
    return first_line or raw_text[:80], notes


@app.route('/api/capture', methods=['POST'])
def api_capture():
    if not TASKS_AVAILABLE:
        return jsonify({'ok': False, 'error': 'Tasks not available'})
    try:
        text = request.json.get('text', '').strip()
        if not text:
            return jsonify({'ok': False})
        title, notes = distill_to_task(text)
        result = create_task(title, notes=notes)
        return jsonify({'ok': bool(result), 'title': title, 'notes': notes})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/meeting-prep', methods=['POST'])
def api_meeting_prep():
    try:
        import anthropic, re as _re
        body = request.json or {}
        meeting_title = body.get('title', '')
        attendees = body.get('attendees', [])  # list of display names
        meeting_time = body.get('time', '')

        # --- Pull relevant Google Tasks ---
        relevant_tasks = []
        if TASKS_AVAILABLE:
            from google_tasks import get_task_lists, get_tasks_hierarchical
            task_lists = get_task_lists()
            keywords = set()
            # Keywords from meeting title
            for w in _re.split(r'[\s\-/]+', meeting_title.lower()):
                if len(w) > 3:
                    keywords.add(w)
            # Keywords from attendee first names
            for a in attendees:
                first = a.split()[0].lower() if a else ''
                if first:
                    keywords.add(first)

            for tl in task_lists:
                for cat in get_tasks_hierarchical(tl['id']):
                    title_lower = cat['name'].lower()
                    notes_lower = ''
                    # Check parent task
                    if any(k in title_lower or k in notes_lower for k in keywords):
                        relevant_tasks.append(cat['name'])
                    # Check subtasks
                    for t in cat.get('tasks', []):
                        t_lower = t.get('title', '').lower()
                        if any(k in t_lower for k in keywords):
                            relevant_tasks.append(t.get('title', ''))

        relevant_tasks = relevant_tasks[:12]

        # --- Pull recent decisions from shared_memory ---
        past_context = []
        if MEMORY_AVAILABLE:
            mem = load_memory()
            keywords_list = list(keywords) if 'keywords' in dir() else []
            for m in reversed(mem.get('meetings', [])[-30:]):
                m_text = (m.get('title', '') + ' ' + str(m.get('signals', {}))).lower()
                if any(k in m_text for k in keywords_list):
                    for d in m.get('signals', {}).get('decisions', []):
                        past_context.append(f"Decision ({m.get('date','')[:10]}): {d}")
                    for a in m.get('signals', {}).get('actions_for_me', []):
                        past_context.append(f"Action from meeting: {a}")
            past_context = past_context[:8]

        # --- Build Claude prompt ---
        context_parts = []
        if relevant_tasks:
            context_parts.append("Open tasks related to this meeting:\n" + "\n".join(f"- {t}" for t in relevant_tasks))
        if past_context:
            context_parts.append("Past decisions/actions:\n" + "\n".join(f"- {c}" for c in past_context))

        context_str = "\n\n".join(context_parts) if context_parts else "No prior context found yet."
        attendees_str = ", ".join(attendees) if attendees else "unknown attendees"

        prompt = (
            f"You are helping Lucas Willett (Director, Customer Support at Visiting Media) prepare for a meeting.\n\n"
            f"Meeting: {meeting_title}\n"
            f"Attendees: {attendees_str}\n"
            f"Time: {meeting_time}\n\n"
            f"Context from support memory:\n{context_str}\n\n"
            f"Write a concise meeting prep brief (4-8 sentences). Include:\n"
            f"- What's open or unresolved that's relevant to this meeting\n"
            f"- What Lucas should get from or communicate to the attendees\n"
            f"- Any decisions or commitments to follow up on\n"
            f"- One clear 'walk in knowing' statement\n\n"
            f"If there's no specific context, give general prep advice for this meeting type.\n"
            f"Be direct. No headers. No bullet points. Just a flowing prep paragraph."
        )

        client = anthropic.Anthropic()
        resp = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=400,
            messages=[{'role': 'user', 'content': prompt}]
        )
        brief = resp.content[0].text.strip()

        return jsonify({'brief': brief, 'tasks': relevant_tasks})

    except Exception as e:
        return jsonify({'error': str(e), 'brief': '', 'tasks': []})


_weather_cache = {'data': None, 'ts': 0}

WMO_ICONS = {
    0: ('☀️', 'Clear'),
    1: ('🌤️', 'Mostly clear'), 2: ('⛅', 'Partly cloudy'), 3: ('☁️', 'Overcast'),
    45: ('🌫️', 'Fog'), 48: ('🌫️', 'Icy fog'),
    51: ('🌦️', 'Light drizzle'), 53: ('🌦️', 'Drizzle'), 55: ('🌧️', 'Heavy drizzle'),
    61: ('🌧️', 'Light rain'), 63: ('🌧️', 'Rain'), 65: ('🌧️', 'Heavy rain'),
    71: ('🌨️', 'Light snow'), 73: ('🌨️', 'Snow'), 75: ('❄️', 'Heavy snow'),
    80: ('🌦️', 'Showers'), 81: ('🌧️', 'Showers'), 82: ('⛈️', 'Heavy showers'),
    95: ('⛈️', 'Thunderstorm'), 96: ('⛈️', 'Thunderstorm'), 99: ('⛈️', 'Thunderstorm'),
}


@app.route('/api/weather')
def api_weather():
    import time, requests as _req
    now_ts = time.time()
    if _weather_cache['data'] and now_ts - _weather_cache['ts'] < 1800:
        return jsonify(_weather_cache['data'])
    try:
        url = (
            'https://api.open-meteo.com/v1/forecast'
            '?latitude=45.3651&longitude=-122.6290'
            '&current=temperature_2m,weathercode,precipitation_probability'
            '&hourly=temperature_2m,precipitation_probability,weathercode'
            '&temperature_unit=fahrenheit'
            '&timezone=America%2FLos_Angeles'
            '&forecast_days=2'
        )
        r = _req.get(url, timeout=8)
        d = r.json()

        cur = d['current']
        code = cur.get('weathercode', 0)
        icon, desc = WMO_ICONS.get(code, ('🌡️', 'Unknown'))
        temp = round(cur['temperature_2m'])

        # Hourly — next 9 hours starting from current hour
        hourly = d['hourly']
        from datetime import datetime as _dt
        local_now = _dt.now()
        cur_hour = local_now.hour

        hours_out = []
        count = 0
        for i, t_str in enumerate(hourly['time']):
            t = _dt.fromisoformat(t_str)
            if t.date() == local_now.date() and t.hour >= cur_hour and count < 9:
                h_code = hourly['weathercode'][i]
                h_icon, _ = WMO_ICONS.get(h_code, ('🌡️', ''))
                rain = hourly['precipitation_probability'][i] or 0
                label = t.strftime('%-I %p').lower()
                hours_out.append({
                    'hour': t.hour,
                    'label': label,
                    'temp': round(hourly['temperature_2m'][i]),
                    'rain': rain,
                    'icon': h_icon,
                })
                count += 1

        result = {
            'temp': temp,
            'icon': icon,
            'description': desc,
            'hours': hours_out,
            'updated': local_now.strftime('%-I:%M %p').lower(),
        }
        _weather_cache['data'] = result
        _weather_cache['ts'] = now_ts
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)})


if __name__ == '__main__':
    port = int(os.environ.get('DASHBOARD_PORT', 5010))
    print(f"Helm Dashboard → http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)

"""Narrative-first UI for AgentTown.

This module contains NARRATIVE_HTML, a complete HTML page that replaces
DASHBOARD_HTML in server.py. It provides two modes:

  - Story Mode (default): An interactive detective novel generator experience
  - Director Mode: The original dashboard with controls, scene graph, puzzle
    checklist, and log tabs

To integrate, assign NARRATIVE_HTML to DASHBOARD_HTML in server.py.
"""

NARRATIVE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
    <title>AgentTown</title>
    <style>
        /* ===== RESET & BASE ===== */
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { height: 100%; overflow: hidden; }
        body {
            font-family: 'Georgia', 'Times New Roman', serif;
            background: #0d1117;
            color: #c9d1d9;
        }

        /* ===== SCROLLBAR ===== */
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: #0d1117; }
        ::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #484f58; }

        /* ===== MODE TOGGLE (top-right corner) ===== */
        #mode-toggle {
            position: fixed; top: 12px; right: 16px; z-index: 100;
            display: flex; align-items: center; gap: 8px;
        }
        #mode-toggle label {
            font-family: monospace; font-size: 11px; color: #8b949e; cursor: pointer;
        }
        #mode-toggle .toggle-switch {
            position: relative; width: 36px; height: 20px; cursor: pointer;
        }
        #mode-toggle .toggle-switch input { opacity: 0; width: 0; height: 0; }
        #mode-toggle .toggle-slider {
            position: absolute; top: 0; left: 0; right: 0; bottom: 0;
            background: #30363d; border-radius: 10px; transition: 0.3s;
        }
        #mode-toggle .toggle-slider::before {
            content: ''; position: absolute; height: 14px; width: 14px;
            left: 3px; bottom: 3px; background: #c9d1d9; border-radius: 50%;
            transition: 0.3s;
        }
        #mode-toggle input:checked + .toggle-slider { background: #e3b341; }
        #mode-toggle input:checked + .toggle-slider::before { transform: translateX(16px); }

        /* ===== STORY MODE CONTAINER ===== */
        #story-mode {
            height: 100%; display: flex; flex-direction: column;
        }

        /* ===== STORY SEED SCREEN ===== */
        #seed-screen {
            flex: 1; display: flex; flex-direction: column; align-items: center;
            justify-content: center; padding: 32px 20px; overflow-y: auto;
        }
        #seed-screen .seed-title {
            font-size: 36px; color: #e3b341; margin-bottom: 6px;
            letter-spacing: 2px; text-align: center;
        }
        #seed-screen .seed-subtitle {
            font-size: 14px; color: #8b949e; font-style: italic;
            margin-bottom: 36px; text-align: center;
        }

        /* Theme cards */
        .theme-cards {
            display: flex; gap: 16px; margin-bottom: 28px; flex-wrap: wrap;
            justify-content: center;
        }
        .theme-card {
            width: 200px; padding: 20px 16px; background: #161b22;
            border: 2px solid #30363d; border-radius: 10px; cursor: pointer;
            transition: all 0.3s; text-align: center;
        }
        .theme-card:hover { border-color: #8b949e; transform: translateY(-2px); }
        .theme-card.selected { border-color: #e3b341; background: #1c1d24; }
        .theme-card .tc-icon { font-size: 32px; margin-bottom: 8px; }
        .theme-card .tc-name {
            font-size: 15px; color: #e6edf3; font-weight: bold; margin-bottom: 6px;
        }
        .theme-card .tc-desc {
            font-size: 11px; color: #8b949e; font-family: monospace; line-height: 1.4;
        }

        /* Seed form */
        .seed-form { width: 100%; max-width: 560px; }
        .seed-form label {
            display: block; font-family: monospace; font-size: 11px;
            color: #8b949e; margin-bottom: 4px; margin-top: 16px;
        }
        .seed-form textarea, .seed-form input, .seed-form select {
            width: 100%; background: #161b22; color: #e6edf3;
            border: 1px solid #30363d; border-radius: 6px;
            padding: 10px 12px; font-family: 'Georgia', serif; font-size: 14px;
            transition: border-color 0.3s;
        }
        .seed-form textarea:focus, .seed-form input:focus, .seed-form select:focus {
            outline: none; border-color: #e3b341;
        }
        .seed-form textarea { resize: vertical; min-height: 80px; }

        .seed-form .difficulty-row {
            display: flex; align-items: center; gap: 16px; margin-top: 16px;
        }
        .seed-form .difficulty-row label { margin: 0; }
        .seed-form .difficulty-row input[type="range"] {
            flex: 1; -webkit-appearance: none; height: 4px; background: #30363d;
            border-radius: 2px; border: none; padding: 0;
        }
        .seed-form .difficulty-row input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none; width: 18px; height: 18px; border-radius: 50%;
            background: #e3b341; cursor: pointer;
        }
        .seed-form .diff-val {
            font-family: monospace; font-size: 16px; color: #e3b341;
            font-weight: bold; min-width: 20px; text-align: center;
        }

        #btn-begin-story {
            display: block; width: 100%; margin-top: 24px; padding: 14px;
            background: linear-gradient(135deg, #e3b341, #c9952e);
            border: none; border-radius: 8px; color: #0d1117;
            font-family: 'Georgia', serif; font-size: 16px; font-weight: bold;
            cursor: pointer; letter-spacing: 1px; transition: opacity 0.3s;
        }
        #btn-begin-story:hover { opacity: 0.9; }
        #btn-begin-story:disabled { opacity: 0.4; cursor: default; }

        /* Typewriter generating text */
        #generating-text {
            display: none; margin-top: 20px; text-align: center;
            font-style: italic; color: #e3b341; font-size: 15px;
        }
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
        #generating-text .cursor {
            display: inline-block; width: 2px; height: 16px;
            background: #e3b341; margin-left: 4px; vertical-align: text-bottom;
            animation: blink 0.8s infinite;
        }

        /* ===== WORLD REVEAL SCREEN ===== */
        #reveal-screen { display: none; flex: 1; flex-direction: column; padding: 32px 20px; overflow-y: auto; align-items: center; }
        .reveal-title {
            font-size: 28px; color: #e3b341; text-align: center; margin-bottom: 8px;
        }
        .reveal-premise {
            font-size: 14px; color: #8b949e; font-style: italic; text-align: center;
            margin-bottom: 24px; max-width: 560px;
        }
        .reveal-section-label {
            font-family: monospace; font-size: 11px; color: #e3b341;
            letter-spacing: 2px; margin-bottom: 10px; text-align: center;
        }

        .reveal-rooms {
            display: flex; gap: 12px; flex-wrap: wrap; justify-content: center;
            margin-bottom: 28px; max-width: 700px;
        }
        .reveal-room {
            background: #161b22; border: 1px solid #30363d; border-radius: 8px;
            padding: 14px 16px; width: 200px; opacity: 0;
            animation: revealFadeIn 0.6s ease forwards;
        }
        .reveal-room .rr-name { font-size: 14px; color: #e6edf3; font-weight: bold; margin-bottom: 4px; }
        .reveal-room .rr-desc { font-size: 11px; color: #8b949e; font-family: monospace; line-height: 1.4; }

        .reveal-characters {
            display: flex; gap: 12px; flex-wrap: wrap; justify-content: center;
            margin-bottom: 28px; max-width: 700px;
        }
        .reveal-char {
            background: #161b22; border: 1px solid #30363d; border-radius: 8px;
            padding: 14px 16px; width: 200px; text-align: center; opacity: 0;
            animation: revealFadeIn 0.6s ease forwards;
        }
        .reveal-char .rc-name { font-size: 15px; color: #58a6ff; font-weight: bold; margin-bottom: 4px; }
        .reveal-char .rc-desc { font-size: 11px; color: #8b949e; font-family: monospace; }

        @keyframes revealFadeIn {
            from { opacity: 0; transform: translateY(12px); }
            to { opacity: 1; transform: translateY(0); }
        }

        #btn-begin-sim {
            margin-top: 8px; margin-bottom: 32px; padding: 12px 40px;
            background: linear-gradient(135deg, #e3b341, #c9952e);
            border: none; border-radius: 8px; color: #0d1117;
            font-family: 'Georgia', serif; font-size: 15px; font-weight: bold;
            cursor: pointer; letter-spacing: 1px; opacity: 0;
            animation: revealFadeIn 0.6s ease forwards;
        }
        #btn-begin-sim:hover { opacity: 0.9; }

        /* ===== STORY FEED (main gameplay) ===== */
        #feed-screen {
            display: none; flex: 1; flex-direction: column; height: 100%;
            overflow: hidden;
        }

        /* Feed header bar */
        #feed-header {
            display: flex; align-items: center; padding: 10px 20px;
            border-bottom: 1px solid #21262d; flex-shrink: 0;
            background: #0a0e14;
        }
        #feed-header .fh-title {
            font-size: 18px; color: #e3b341; flex: 1;
        }
        #feed-controls {
            display: flex; align-items: center; gap: 6px;
        }
        #feed-controls button {
            font-family: monospace; font-size: 11px; padding: 4px 12px;
            border: 1px solid #30363d; border-radius: 4px; cursor: pointer;
            background: #21262d; color: #c9d1d9; transition: all 0.2s;
        }
        #feed-controls button:hover:not(:disabled) { background: #30363d; border-color: #58a6ff; }
        #feed-controls button:disabled { opacity: 0.4; cursor: default; }
        #feed-controls button.active { background: #1f6feb; border-color: #58a6ff; color: #fff; }
        #feed-controls .sep { color: #30363d; margin: 0 2px; }
        #feed-status {
            font-family: monospace; font-size: 11px; color: #3fb950; margin-left: 8px;
        }
        #feed-token-display {
            margin-left: 12px; font-family: monospace; font-size: 12px;
            font-weight: bold; color: #e3b341; background: #2d2006;
            padding: 3px 10px; border-radius: 4px; border: 1px solid #e3b341;
        }

        /* Feed body: scrollable narrative cards */
        #feed-body {
            flex: 1; display: flex; flex-direction: column; overflow: hidden;
        }

        /* Progress bar */
        #progress-bar-container {
            padding: 8px 20px; flex-shrink: 0; border-bottom: 1px solid #21262d;
        }
        #progress-bar-container .pb-label {
            font-family: monospace; font-size: 11px; color: #8b949e; margin-bottom: 4px;
        }
        .progress-track {
            width: 100%; height: 6px; background: #21262d; border-radius: 3px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%; background: linear-gradient(90deg, #e3b341, #3fb950);
            border-radius: 3px; width: 0%; transition: width 0.5s ease;
        }

        /* Card area */
        #card-viewport {
            flex: 1; display: flex; align-items: center; justify-content: center;
            padding: 20px; overflow: hidden; position: relative;
        }
        .feed-card {
            background: #161b22; border: 1px solid #30363d; border-radius: 12px;
            padding: 28px 32px; max-width: 720px; width: 100%;
            line-height: 1.9; font-size: 16px; color: #e6edf3;
            box-shadow: 0 4px 24px rgba(0,0,0,0.5);
            min-height: 120px;
        }
        .feed-card .fc-chapter {
            font-family: monospace; font-size: 11px; color: #e3b341;
            letter-spacing: 2px; margin-bottom: 12px;
        }
        .feed-card .fc-narrative { margin-bottom: 16px; }
        .feed-card .fc-events {
            font-family: 'Courier New', monospace; font-size: 11px;
            color: #8b949e; border-top: 1px solid #21262d; padding-top: 12px;
            line-height: 1.6;
        }
        .feed-card .fc-events .ev-line { padding: 1px 0; }
        .feed-card.finished { border-color: #3fb950; }
        .feed-card.finished .fc-chapter { color: #3fb950; }

        /* Card navigation */
        #card-nav {
            display: flex; align-items: center; justify-content: center; gap: 12px;
            padding: 10px; flex-shrink: 0; border-top: 1px solid #21262d;
        }
        #card-nav button {
            font-family: monospace; font-size: 16px; width: 36px; height: 36px;
            border: 1px solid #30363d; border-radius: 6px; cursor: pointer;
            background: #21262d; color: #c9d1d9; transition: border-color 0.2s;
        }
        #card-nav button:hover:not(:disabled) { border-color: #58a6ff; }
        #card-nav button:disabled { opacity: 0.3; cursor: default; }
        #card-nav .nav-info {
            font-family: monospace; font-size: 11px; color: #8b949e;
            min-width: 60px; text-align: center;
        }

        /* Agent strip at bottom */
        #agent-strip {
            display: flex; gap: 8px; padding: 10px 20px; flex-shrink: 0;
            border-top: 1px solid #21262d; overflow-x: auto;
            background: #0a0e14;
        }
        .as-card {
            flex-shrink: 0; background: #161b22; border: 1px solid #30363d;
            border-radius: 6px; padding: 6px 10px; font-family: monospace;
            font-size: 11px; min-width: 140px;
        }
        .as-card .as-name { color: #58a6ff; font-weight: bold; font-size: 12px; }
        .as-card .as-loc { color: #8b949e; margin-top: 2px; }
        .as-card .as-inv { color: #3fb950; font-size: 10px; margin-top: 2px; }

        /* ===== DIRECTOR MODE ===== */
        #director-mode {
            display: none; height: 100%;
        }
        #director-mode.visible { display: flex; }
        #story-mode.hidden { display: none; }

        /* Director layout: left + right panels */
        #dir-left {
            flex: 3; padding: 24px; overflow-y: auto;
            border-right: 1px solid #21262d; display: flex; flex-direction: column;
        }
        #dir-left h1 { color: #e3b341; font-size: 24px; margin-bottom: 4px; }
        .dir-subtitle { color: #8b949e; font-style: italic; margin-bottom: 12px; font-size: 13px; }

        #dir-controls {
            display: flex; align-items: center; gap: 8px; margin-bottom: 12px;
        }
        #dir-controls button {
            font-family: monospace; font-size: 11px; padding: 4px 12px;
            border: 1px solid #30363d; border-radius: 4px; cursor: pointer;
            background: #21262d; color: #c9d1d9; transition: all 0.2s;
        }
        #dir-controls button:hover:not(:disabled) { background: #30363d; border-color: #58a6ff; }
        #dir-controls button:disabled { opacity: 0.4; cursor: default; }
        #dir-controls button.active { background: #1f6feb; border-color: #58a6ff; color: #fff; }
        #dir-controls .sep { color: #30363d; margin: 0 2px; }
        #dir-status { color: #3fb950; font-family: monospace; font-size: 11px; }
        #dir-token-display {
            margin-left: auto;
            font-family: monospace; font-size: 12px; font-weight: bold;
            color: #e3b341; background: #2d2006; padding: 3px 10px;
            border-radius: 4px; border: 1px solid #e3b341;
        }

        #dir-save-list {
            background: #161b22; border: 1px solid #30363d; border-radius: 6px;
            padding: 10px; font-family: monospace; font-size: 11px; max-height: 150px; overflow-y: auto;
        }
        .save-entry {
            display: flex; justify-content: space-between; align-items: center;
            padding: 4px 6px; border-bottom: 1px solid #21262d;
        }
        .save-entry:last-child { border-bottom: none; }
        .save-entry .save-info { color: #8b949e; }
        .save-entry .save-name { color: #e6edf3; font-weight: bold; }
        .save-entry button {
            font-family: monospace; font-size: 10px; padding: 2px 8px;
            border: 1px solid #30363d; border-radius: 3px; cursor: pointer;
            background: #21262d; color: #c9d1d9; margin-left: 6px;
        }
        .save-entry button:hover { border-color: #58a6ff; }
        .save-entry button.del:hover { border-color: #f85149; color: #f85149; }

        /* Director story card viewer */
        #dir-story { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
        #dir-card-container {
            flex: 1; display: flex; align-items: center; justify-content: center;
            position: relative; overflow: hidden; padding: 10px;
        }
        .story-card {
            background: #161b22; border: 1px solid #30363d; border-radius: 10px;
            padding: 24px; max-width: 100%; width: 100%;
            line-height: 1.8; font-size: 15px; color: #e6edf3;
            box-shadow: 0 4px 20px rgba(0,0,0,0.4);
            min-height: 120px;
        }
        .story-card .chapter-num {
            color: #e3b341; font-family: monospace; font-size: 11px;
            margin-bottom: 10px; letter-spacing: 1px;
        }
        .story-card .card-events {
            color: #8b949e; font-family: monospace; font-size: 10px;
            margin-top: 12px; padding-top: 10px; border-top: 1px solid #21262d;
        }
        .story-card.finished { border-color: #3fb950; }
        .story-card.finished .chapter-num { color: #3fb950; }
        #dir-story-nav {
            display: flex; align-items: center; justify-content: center; gap: 12px;
            padding: 10px; flex-shrink: 0;
        }
        #dir-story-nav button {
            font-family: monospace; font-size: 16px; width: 36px; height: 36px;
            border: 1px solid #30363d; border-radius: 6px; cursor: pointer;
            background: #21262d; color: #c9d1d9;
        }
        #dir-story-nav button:hover:not(:disabled) { border-color: #58a6ff; }
        #dir-story-nav button:disabled { opacity: 0.3; cursor: default; }
        #dir-story-nav .page-info {
            color: #8b949e; font-family: monospace; font-size: 11px;
            min-width: 60px; text-align: center;
        }
        #dir-btn-copy-scene {
            font-family: monospace; font-size: 11px; padding: 4px 10px;
            border: 1px solid #e3b341; border-radius: 4px; cursor: pointer;
            background: #2d2006; color: #e3b341;
        }
        #dir-btn-copy-scene:hover { background: #3d3010; }

        /* Right panel */
        #dir-right {
            flex: 2; display: flex; flex-direction: column; background: #0a0e14;
        }
        #dir-map-panel { padding: 16px; border-bottom: 1px solid #21262d; }
        #dir-map-panel h2 { color: #e3b341; font-size: 13px; margin-bottom: 10px; font-family: monospace; }
        #dir-scene-graph svg { width: 100%; height: auto; }

        #dir-puzzle-panel { padding: 16px; border-bottom: 1px solid #21262d; }
        #dir-puzzle-panel h2 { color: #d2a8ff; font-size: 13px; margin-bottom: 10px; font-family: monospace; }
        .puzzle-row {
            display: flex; align-items: center; gap: 8px;
            font-family: monospace; font-size: 11px; padding: 6px 8px;
            background: #161b22; border-radius: 4px; margin-bottom: 4px;
        }
        .puzzle-icon { font-size: 14px; width: 20px; text-align: center; }
        .puzzle-name { color: #e6edf3; flex: 1; }
        .puzzle-status { padding: 2px 8px; border-radius: 3px; font-size: 10px; font-weight: bold; }
        .puzzle-status.locked { background: #3d1f1f; color: #f85149; }
        .puzzle-status.solved { background: #1a3a1a; color: #3fb950; }
        .puzzle-status.partial { background: #3d3520; color: #e3b341; }

        #dir-agent-panel { padding: 16px; border-bottom: 1px solid #21262d; }
        #dir-agent-panel h2 { color: #58a6ff; font-size: 13px; margin-bottom: 10px; font-family: monospace; }
        #dir-agent-list { display: flex; gap: 8px; }
        .agent-card {
            flex: 1; background: #161b22; border: 1px solid #30363d;
            border-radius: 6px; padding: 8px 10px; font-family: monospace; font-size: 11px;
        }
        .agent-card .agent-name { color: #58a6ff; font-weight: bold; font-size: 12px; margin-bottom: 4px; }
        .agent-card .agent-location { color: #8b949e; margin-bottom: 3px; }
        .agent-card .agent-inv { color: #3fb950; font-size: 10px; }
        .agent-card .agent-inv-empty { color: #484f58; font-size: 10px; }

        #dir-log-panel {
            flex: 1; display: flex; flex-direction: column; overflow: hidden;
            font-family: 'Courier New', monospace; font-size: 11px;
        }
        .log-tabs { display: flex; gap: 0; padding: 8px 16px 0; flex-shrink: 0; }
        .log-tab {
            padding: 4px 14px; cursor: pointer; font-family: monospace; font-size: 11px;
            border: 1px solid #30363d; border-bottom: none; border-radius: 4px 4px 0 0;
            background: #0a0e14; color: #8b949e;
        }
        .log-tab.active { background: #161b22; color: #58a6ff; border-color: #58a6ff; }
        .log-content { flex: 1; overflow-y: auto; padding: 12px 16px; }
        #dir-server-log { display: none; white-space: pre-wrap; line-height: 1.5; }
        #dir-server-log .sl-tick { color: #e3b341; font-weight: bold; }
        #dir-server-log .sl-action { color: #f0f6fc; }
        #dir-server-log .sl-event { color: #79c0ff; }
        #dir-server-log .sl-memory { color: #d2a8ff; }
        #dir-server-log .sl-token { color: #3fb950; }
        #dir-server-log .sl-error { color: #f85149; }
        .tick-group { margin-bottom: 8px; border-left: 2px solid #30363d; padding-left: 8px; }
        .tick-label { color: #8b949e; font-size: 10px; margin-bottom: 2px; }
        .event { padding: 1px 0; font-size: 11px; }
        .event.move { color: #79c0ff; }
        .event.pick_up { color: #3fb950; }
        .event.drop { color: #d29922; }
        .event.use { color: #d2a8ff; }
        .event.examine { color: #58a6ff; }
        .event.talk { color: #f0f6fc; }
        .event.fail { color: #f85149; }
        .event.state_change { color: #e3b341; }
        .event.wait { color: #484f58; }

        #copy-toast {
            position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
            background: #3fb950; color: #0d1117; padding: 8px 20px; border-radius: 6px;
            font-family: monospace; font-size: 12px; display: none; z-index: 999;
        }

        /* ===== MOBILE ===== */
        @media (max-width: 900px) {
            #seed-screen { padding: 20px 12px; }
            #seed-screen .seed-title { font-size: 24px; }
            .theme-cards { gap: 10px; }
            .theme-card { width: 160px; padding: 14px 10px; }
            .theme-card .tc-icon { font-size: 24px; }
            .theme-card .tc-name { font-size: 13px; }

            .feed-card { padding: 18px 16px; font-size: 14px; line-height: 1.7; }
            .feed-card .fc-chapter { font-size: 10px; }
            .feed-card .fc-events { font-size: 10px; }
            #feed-header { padding: 8px 12px; flex-wrap: wrap; }
            #feed-header .fh-title { font-size: 14px; }
            #feed-controls { flex-wrap: wrap; gap: 3px; }
            #feed-controls button { font-size: 10px; padding: 3px 8px; }
            #feed-controls .sep { display: none; }
            #feed-token-display { font-size: 10px; padding: 2px 6px; }
            #agent-strip { padding: 6px 12px; }
            .as-card { min-width: 120px; padding: 4px 8px; font-size: 10px; }

            #director-mode.visible { flex-direction: column; height: auto; min-height: 100vh; }
            #dir-left { flex: none; border-right: none; padding: 12px; border-bottom: 1px solid #21262d; }
            #dir-left h1 { font-size: 18px; }
            #dir-controls { flex-wrap: wrap; gap: 4px; }
            #dir-controls button { font-size: 10px; padding: 3px 8px; }
            #dir-controls .sep { display: none; }
            #dir-token-display { font-size: 10px; padding: 2px 6px; margin-left: 0; margin-top: 4px; width: 100%; text-align: center; }
            #dir-right { flex: none; }
            #dir-map-panel { padding: 10px; }
            .agent-card { font-size: 10px; padding: 6px; }
            #dir-log-panel { max-height: 40vh; }
            .log-tabs { padding: 6px 10px 0; }
            .log-tab { font-size: 10px; padding: 3px 10px; }
            .log-content { padding: 8px 10px; font-size: 10px; }
        }
    </style>
</head>
<body>

<!-- ===== MODE TOGGLE ===== -->
<div id="mode-toggle">
    <label for="mode-switch">Story</label>
    <div class="toggle-switch">
        <input type="checkbox" id="mode-switch" onchange="toggleMode()">
        <span class="toggle-slider"></span>
    </div>
    <label for="mode-switch">Director</label>
</div>

<!-- ========================================= -->
<!-- STORY MODE                                -->
<!-- ========================================= -->
<div id="story-mode">

    <!-- Screen 1: Story Seed -->
    <div id="seed-screen">
        <div class="seed-title">AgentTown</div>
        <div class="seed-subtitle">An interactive detective novel generator</div>

        <div class="theme-cards" id="theme-cards">
            <div class="theme-card selected" data-theme="gothic_manor" onclick="selectTheme(this)">
                <div class="tc-icon">&#x1F3DA;</div>
                <div class="tc-name">Gothic Manor</div>
                <div class="tc-desc">Crumbling halls, hidden passages, dark secrets</div>
            </div>
            <div class="theme-card" data-theme="sci_fi_lab" onclick="selectTheme(this)">
                <div class="tc-icon">&#x1F52C;</div>
                <div class="tc-name">Sci-Fi Lab</div>
                <div class="tc-desc">Rogue AI, quarantine zones, unstable experiments</div>
            </div>
            <div class="theme-card" data-theme="ancient_tomb" onclick="selectTheme(this)">
                <div class="tc-icon">&#x1F3DB;</div>
                <div class="tc-name">Ancient Tomb</div>
                <div class="tc-desc">Cursed relics, trapped corridors, forgotten rituals</div>
            </div>
        </div>

        <div class="seed-form">
            <label>Premise (what drives the story?)</label>
            <textarea id="seed-premise" placeholder="e.g. Three investigators enter the abandoned Blackwood Manor after receiving an anonymous letter. They must uncover the truth behind the disappearances before the manor claims them too..."></textarea>

            <div class="difficulty-row">
                <label>Difficulty</label>
                <input type="range" id="seed-difficulty" min="2" max="5" value="3" oninput="updateDiffLabel()">
                <span class="diff-val" id="diff-label">3</span>
            </div>

            <button id="btn-begin-story" onclick="beginStory()">Begin Story</button>
        </div>

        <div id="generating-text">
            <span id="gen-text-content">The narrator sets the scene...</span><span class="cursor"></span>
        </div>
    </div>

    <!-- Screen 2: World Reveal -->
    <div id="reveal-screen">
        <div class="reveal-title" id="reveal-title">The World Awakens</div>
        <div class="reveal-premise" id="reveal-premise"></div>

        <div class="reveal-section-label">LOCATIONS</div>
        <div class="reveal-rooms" id="reveal-rooms"></div>

        <div class="reveal-section-label">CHARACTERS</div>
        <div class="reveal-characters" id="reveal-chars"></div>

        <button id="btn-begin-sim" onclick="beginSimulation()">Begin the Story</button>
    </div>

    <!-- Screen 3: Story Feed -->
    <div id="feed-screen">
        <div id="feed-header">
            <div class="fh-title" id="feed-title">AgentTown</div>
            <div id="feed-controls">
                <button id="feed-btn-pause" onclick="simPause()">Pause</button>
                <button id="feed-btn-resume" onclick="simResume()" disabled>Resume</button>
                <button id="feed-btn-step" onclick="simStep()" disabled>Step</button>
                <span class="sep">|</span>
                <button id="feed-btn-save" onclick="simSave()">Save</button>
                <button id="feed-btn-load" onclick="toggleSaveList()">Load</button>
                <button id="feed-btn-reset" onclick="simReset()" style="color:#f85149">Reset</button>
                <span id="feed-status">Connecting...</span>
                <span id="feed-token-display">Tokens: 0</span>
            </div>
        </div>
        <div id="feed-save-list" style="display:none; padding: 0 20px;">
            <div id="feed-save-content" style="background:#161b22;border:1px solid #30363d;border-radius:6px;padding:10px;font-family:monospace;font-size:11px;max-height:150px;overflow-y:auto;margin-bottom:8px;"></div>
        </div>
        <div id="feed-body">
            <div id="progress-bar-container">
                <div class="pb-label" id="pb-label">Puzzle progress: 0/0 steps</div>
                <div class="progress-track">
                    <div class="progress-fill" id="progress-fill"></div>
                </div>
            </div>
            <div id="card-viewport">
                <div class="feed-card" id="feed-current-card">
                    <div class="fc-chapter">Waiting for first tick...</div>
                </div>
            </div>
            <div id="card-nav">
                <button id="feed-btn-prev" onclick="feedPrevCard()" disabled>&lt;</button>
                <span class="nav-info" id="feed-page-info">0 / 0</span>
                <button id="feed-btn-next" onclick="feedNextCard()" disabled>&gt;</button>
            </div>
        </div>
        <div id="agent-strip"></div>
    </div>
</div>

<!-- ========================================= -->
<!-- DIRECTOR MODE                             -->
<!-- ========================================= -->
<div id="director-mode">
    <div id="dir-left">
        <h1>Ravenwood Manor</h1>
        <div class="dir-subtitle">An escape room experience</div>
        <div id="dir-controls">
            <button id="dir-btn-pause" onclick="simPause()">Pause</button>
            <button id="dir-btn-resume" onclick="simResume()" disabled>Resume</button>
            <button id="dir-btn-step" onclick="simStep()" disabled>Step 1 Tick</button>
            <span class="sep">|</span>
            <button id="dir-btn-save" onclick="simSave()">Save</button>
            <button id="dir-btn-load" onclick="toggleSaveList()">Load</button>
            <button id="dir-btn-reset" onclick="simReset()" style="color:#f85149">Reset</button>
            <button id="dir-btn-create" onclick="toggleCreator()" style="color:#e3b341">Create</button>
            <span id="dir-status">Connecting...</span>
            <span id="dir-token-display">Tokens: 0</span>
        </div>
        <div id="dir-save-list" style="display:none; margin-bottom: 12px;"></div>
        <div id="dir-story">
            <div id="dir-card-container">
                <div class="story-card" id="dir-current-card">
                    <div class="chapter-num">Waiting for first tick...</div>
                </div>
            </div>
            <div id="dir-story-nav">
                <button id="dir-btn-prev" onclick="dirPrevCard()" disabled>&lt;</button>
                <span class="page-info" id="dir-page-info">0 / 0</span>
                <button id="dir-btn-next" onclick="dirNextCard()" disabled>&gt;</button>
                <button id="dir-btn-copy-scene" onclick="copyScene()">Copy Scene</button>
            </div>
        </div>

        <!-- Map Creator Modal (Reverse Architect) -->
        <div id="creator-overlay" style="display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.85); z-index:1000; overflow-y:auto; padding:12px;">
            <div style="max-width:600px; margin:0 auto; background:#161b22; border:1px solid #30363d; border-radius:10px; padding:16px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                    <h2 style="color:#e3b341; font-size:16px; font-family:monospace;">Escape Room Architect</h2>
                    <button onclick="toggleCreator()" style="background:none; border:1px solid #30363d; color:#8b949e; border-radius:4px; padding:3px 8px; cursor:pointer; font-family:monospace; font-size:11px;">Close</button>
                </div>
                <div style="margin-bottom:12px;">
                    <label style="color:#8b949e; font-family:monospace; font-size:10px; margin-bottom:4px; display:block;">Quick Presets</label>
                    <div id="preset-buttons" style="display:flex; gap:4px; flex-wrap:wrap;"></div>
                </div>
                <div style="display:flex; gap:8px; margin-bottom:8px;">
                    <div style="flex:1;">
                        <label style="color:#8b949e; font-family:monospace; font-size:10px;">Builder</label>
                        <input id="arc-builder" placeholder="Mad Scientist, Pharaoh..." style="width:100%; background:#0d1117; color:#e6edf3; border:1px solid #30363d; border-radius:4px; padding:6px; font-family:monospace; font-size:13px;">
                    </div>
                    <div style="flex:1;">
                        <label style="color:#8b949e; font-family:monospace; font-size:10px;">Protects</label>
                        <input id="arc-goal" placeholder="Secret formula, treasure..." style="width:100%; background:#0d1117; color:#e6edf3; border:1px solid #30363d; border-radius:4px; padding:6px; font-family:monospace; font-size:13px;">
                    </div>
                </div>
                <div style="margin-bottom:8px;">
                    <label style="color:#8b949e; font-family:monospace; font-size:10px;">Background</label>
                    <textarea id="arc-background" rows="2" placeholder="Scene description..." style="width:100%; background:#0d1117; color:#e6edf3; border:1px solid #30363d; border-radius:4px; padding:6px; font-family:monospace; font-size:12px; resize:vertical;"></textarea>
                </div>
                <div style="display:flex; gap:12px; margin-bottom:12px; align-items:center;">
                    <div>
                        <label style="color:#8b949e; font-family:monospace; font-size:10px;">Difficulty</label>
                        <select id="arc-difficulty" onchange="updateEndingPreview()" style="background:#0d1117; color:#e6edf3; border:1px solid #30363d; border-radius:4px; padding:4px 8px; font-family:monospace; font-size:13px;">
                            <option value="2">2 - Simple</option>
                            <option value="3" selected>3 - Medium</option>
                            <option value="4">4 - Complex</option>
                            <option value="5">5 - Epic</option>
                        </select>
                    </div>
                    <div id="ending-preview" style="display:flex; gap:4px; flex-wrap:wrap;"></div>
                </div>
                <div style="display:flex; gap:6px; margin-bottom:10px;">
                    <button onclick="previewMap()" id="btn-preview" style="flex:1; padding:8px; background:#21262d; border:1px solid #58a6ff; border-radius:6px; color:#58a6ff; font-family:monospace; font-size:12px; cursor:pointer; font-weight:bold;">Preview Map</button>
                    <button onclick="previewMap()" id="btn-regenerate" style="flex:1; padding:8px; background:#21262d; border:1px solid #e3b341; border-radius:6px; color:#e3b341; font-family:monospace; font-size:12px; cursor:pointer; font-weight:bold; display:none;">Regenerate</button>
                    <button onclick="playPreviewedMap()" id="btn-play-map" style="flex:1; padding:8px; background:#1f6feb; border:none; border-radius:6px; color:#fff; font-family:monospace; font-size:12px; cursor:pointer; font-weight:bold; display:none;">Play This Map</button>
                </div>
                <div id="creator-status" style="color:#8b949e; font-family:monospace; font-size:11px; margin-bottom:8px;"></div>
                <div id="preview-container" style="display:none;">
                    <div id="preview-stats" style="display:flex; gap:8px; margin-bottom:8px; flex-wrap:wrap;"></div>
                    <div id="preview-graph" style="background:#0d1117; border:1px solid #30363d; border-radius:6px; padding:8px; overflow:hidden;"></div>
                    <div id="preview-endings" style="margin-top:8px;"></div>
                </div>
            </div>
        </div>
    </div>
    <div id="dir-right">
        <div id="dir-map-panel">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <h2>SCENE VIEW</h2>
                <button onclick="toggleFullscreenScene()" style="background:none;border:1px solid #30363d;color:#8b949e;border-radius:3px;padding:2px 6px;cursor:pointer;font-family:monospace;font-size:10px;">Fullscreen</button>
            </div>
            <div id="dir-scene-graph"></div>
        </div>
        <div id="dir-puzzle-panel">
            <h2>PUZZLE PROGRESS</h2>
            <div id="dir-puzzle-list"></div>
        </div>
        <div id="dir-agent-panel">
            <h2>AGENTS</h2>
            <div id="dir-agent-list"></div>
        </div>
        <div id="dir-log-panel">
            <div class="log-tabs">
                <div class="log-tab active" onclick="switchLogTab('dir-events', this)">Events</div>
                <div class="log-tab" onclick="switchLogTab('dir-server-log', this)">Server Log</div>
            </div>
            <div id="dir-events" class="log-content"></div>
            <div id="dir-server-log" class="log-content"></div>
        </div>
    </div>
</div>

<div id="copy-toast">Copied to clipboard!</div>

<script>
// ================================================================
// STATE
// ================================================================
let currentMode = 'story'; // 'story' or 'director'
let storyScreen = 'seed';  // 'seed', 'reveal', 'feed'
let selectedTheme = 'gothic_manor';
let isPaused = true;
let worldBible = null;

// Feed story cards
const feedCards = [];
let feedCardIdx = -1;
let feedAutoFollow = true;

// Director story cards (shared data, independent navigation)
const dirCards = [];
let dirCardIdx = -1;
let dirAutoFollow = true;

// Escape chain
let escapeChain = [];

// Agent colors
const AGENT_COLORS = ['#58a6ff', '#f78166', '#3fb950', '#d2a8ff'];

// ================================================================
// MODE TOGGLE
// ================================================================
function toggleMode() {
    const sw = document.getElementById('mode-switch');
    currentMode = sw.checked ? 'director' : 'story';
    const storyEl = document.getElementById('story-mode');
    const dirEl = document.getElementById('director-mode');
    if (currentMode === 'director') {
        storyEl.classList.add('hidden');
        dirEl.classList.add('visible');
    } else {
        storyEl.classList.remove('hidden');
        dirEl.classList.remove('visible');
    }
}

// ================================================================
// STORY MODE: SEED SCREEN
// ================================================================
function selectTheme(el) {
    document.querySelectorAll('.theme-card').forEach(c => c.classList.remove('selected'));
    el.classList.add('selected');
    selectedTheme = el.getAttribute('data-theme');
}

function updateDiffLabel() {
    document.getElementById('diff-label').textContent = document.getElementById('seed-difficulty').value;
}

// Load theme data from server to enrich cards
function loadThemes() {
    fetch('/api/themes').then(r => r.json()).then(data => {
        if (!data.themes) return;
        const cards = document.querySelectorAll('.theme-card');
        cards.forEach(card => {
            const key = card.getAttribute('data-theme');
            const t = data.themes[key];
            if (t && t.rooms) {
                const roomNames = t.rooms.map(r => r.name || r).slice(0, 3).join(', ');
                const descEl = card.querySelector('.tc-desc');
                if (descEl && roomNames) {
                    descEl.textContent = descEl.textContent + '. Rooms: ' + roomNames;
                }
            }
        });
    }).catch(() => {});
}

// Typewriter effect
let typewriterTimer = null;
const genPhrases = [
    'The narrator sets the scene...',
    'Drawing the blueprints of fate...',
    'Populating the rooms with shadows...',
    'Weaving the threads of mystery...',
    'Placing the final pieces...',
];

function startTypewriter() {
    const el = document.getElementById('gen-text-content');
    const container = document.getElementById('generating-text');
    container.style.display = 'block';
    let phraseIdx = 0;
    el.textContent = genPhrases[0];
    typewriterTimer = setInterval(() => {
        phraseIdx = (phraseIdx + 1) % genPhrases.length;
        el.textContent = genPhrases[phraseIdx];
    }, 3000);
}

function stopTypewriter() {
    if (typewriterTimer) { clearInterval(typewriterTimer); typewriterTimer = null; }
    document.getElementById('generating-text').style.display = 'none';
}

function beginStory() {
    const premise = document.getElementById('seed-premise').value.trim();
    const difficulty = parseInt(document.getElementById('seed-difficulty').value);

    if (!premise) {
        document.getElementById('seed-premise').style.borderColor = '#f85149';
        document.getElementById('seed-premise').focus();
        setTimeout(() => { document.getElementById('seed-premise').style.borderColor = '#30363d'; }, 2000);
        return;
    }

    const btn = document.getElementById('btn-begin-story');
    btn.disabled = true;
    btn.textContent = 'Generating...';
    startTypewriter();

    fetch('/api/generate-story', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            theme: selectedTheme,
            premise: premise,
            difficulty: difficulty,
            num_characters: 3,
        }),
    }).then(r => r.json()).then(data => {
        stopTypewriter();
        btn.disabled = false;
        btn.textContent = 'Begin Story';

        if (data.error) {
            alert('Generation failed: ' + data.error);
            return;
        }

        worldBible = data.world_bible || null;
        showRevealScreen(data);
    }).catch(err => {
        stopTypewriter();
        btn.disabled = false;
        btn.textContent = 'Begin Story';
        alert('Error: ' + err);
    });
}

// ================================================================
// STORY MODE: REVEAL SCREEN
// ================================================================
function showRevealScreen(data) {
    const seedScreen = document.getElementById('seed-screen');
    const revealScreen = document.getElementById('reveal-screen');

    seedScreen.style.display = 'none';
    revealScreen.style.display = 'flex';

    // Title
    const themeNames = {gothic_manor: 'Gothic Manor', sci_fi_lab: 'Sci-Fi Lab', ancient_tomb: 'Ancient Tomb'};
    const title = worldBible ? (worldBible.inciting_incident || themeNames[selectedTheme] || 'The World Awakens') : themeNames[selectedTheme] || 'The World Awakens';
    document.getElementById('reveal-title').textContent = title.length > 60 ? title.substring(0, 60) + '...' : title;

    const premise = worldBible ? worldBible.premise : document.getElementById('seed-premise').value;
    document.getElementById('reveal-premise').textContent = premise;

    // We'll get room/character data from the snapshot that the server broadcasts
    // For now, show what we know from the generation response
    const roomsDiv = document.getElementById('reveal-rooms');
    const charsDiv = document.getElementById('reveal-chars');
    roomsDiv.innerHTML = '';
    charsDiv.innerHTML = '';

    // Characters from world_bible
    if (worldBible && worldBible.characters) {
        worldBible.characters.forEach((ch, i) => {
            const card = document.createElement('div');
            card.className = 'reveal-char';
            card.style.animationDelay = (i * 0.2) + 's';
            card.innerHTML = `<div class="rc-name">${ch.name || 'Agent ' + (i+1)}</div>
                <div class="rc-desc">${ch.description || ch.role || ''}</div>`;
            charsDiv.appendChild(card);
        });
    }

    // Rooms will be populated by snapshot -- use pending snapshot data
    if (pendingSnapshot) {
        populateRevealRooms(pendingSnapshot);
        pendingSnapshot = null;
    }

    // Set button animation delay
    const btn = document.getElementById('btn-begin-sim');
    const totalItems = (worldBible && worldBible.characters ? worldBible.characters.length : 0);
    btn.style.animationDelay = (totalItems * 0.2 + 0.5) + 's';
}

let pendingSnapshot = null;

function populateRevealRooms(snapshot) {
    if (!snapshot || !snapshot.rooms) return;
    const roomsDiv = document.getElementById('reveal-rooms');
    if (roomsDiv.children.length > 0) return; // already populated

    const rooms = Object.values(snapshot.rooms);
    rooms.forEach((room, i) => {
        const card = document.createElement('div');
        card.className = 'reveal-room';
        card.style.animationDelay = (i * 0.15) + 's';
        card.innerHTML = `<div class="rr-name">${room.name}</div>
            <div class="rr-desc">${room.description || ''}</div>`;
        roomsDiv.appendChild(card);
    });
}

// ================================================================
// STORY MODE: FEED SCREEN
// ================================================================
function beginSimulation() {
    const revealScreen = document.getElementById('reveal-screen');
    const feedScreen = document.getElementById('feed-screen');
    revealScreen.style.display = 'none';
    feedScreen.style.display = 'flex';
    storyScreen = 'feed';

    // Set title
    const themeNames = {gothic_manor: 'Gothic Manor', sci_fi_lab: 'Sci-Fi Lab', ancient_tomb: 'Ancient Tomb'};
    document.getElementById('feed-title').textContent = themeNames[selectedTheme] || 'AgentTown';

    // Start in paused state, user presses Resume
    setButtonState(true);
    updateFeedStatus('Paused -- press Resume or Step to begin', '#e3b341');
}

// Jump directly to feed (for reconnect / existing game)
function jumpToFeed() {
    document.getElementById('seed-screen').style.display = 'none';
    document.getElementById('reveal-screen').style.display = 'none';
    document.getElementById('feed-screen').style.display = 'flex';
    storyScreen = 'feed';
}

// Feed card system
function addFeedCard(data) {
    feedCards.push(data);
    dirCards.push(data);
    if (feedAutoFollow) { feedCardIdx = feedCards.length - 1; renderFeedCard(); }
    else { updateFeedNav(); }
    if (dirAutoFollow) { dirCardIdx = dirCards.length - 1; renderDirCard(); }
    else { updateDirNav(); }
}

function renderFeedCard() {
    if (feedCardIdx < 0 || feedCardIdx >= feedCards.length) return;
    const c = feedCards[feedCardIdx];
    const card = document.getElementById('feed-current-card');
    const isFinished = c.finished;

    let html = `<div class="fc-chapter">CHAPTER ${c.tick + 1}</div>`;
    html += `<div class="fc-narrative">${(c.narrative || 'No narration.').replace(/\\n/g, '<br>')}</div>`;
    if (c.events && c.events.length) {
        html += `<div class="fc-events">${c.events.map(e => `<div class="ev-line">${e.description}</div>`).join('')}</div>`;
    }
    card.innerHTML = html;
    card.className = 'feed-card' + (isFinished ? ' finished' : '');
    updateFeedNav();
}

function updateFeedNav() {
    const total = feedCards.length;
    document.getElementById('feed-page-info').textContent = total > 0 ? `${feedCardIdx + 1} / ${total}` : '0 / 0';
    document.getElementById('feed-btn-prev').disabled = feedCardIdx <= 0;
    document.getElementById('feed-btn-next').disabled = feedCardIdx >= total - 1;
}

function feedPrevCard() {
    if (feedCardIdx > 0) { feedCardIdx--; feedAutoFollow = false; renderFeedCard(); }
}
function feedNextCard() {
    if (feedCardIdx < feedCards.length - 1) {
        feedCardIdx++;
        if (feedCardIdx === feedCards.length - 1) feedAutoFollow = true;
        renderFeedCard();
    }
}

// Feed agent strip
function updateAgentStrip(wsData) {
    if (!wsData) return;
    const agents = wsData.agents || {};
    const rooms = wsData.rooms || {};
    const strip = document.getElementById('agent-strip');
    let html = '';
    for (const a of Object.values(agents)) {
        const roomName = rooms[a.room_id] ? rooms[a.room_id].name : a.room_id;
        const inv = (a.inventory || []).map(i => i.name);
        const invStr = inv.length ? inv.join(', ') : 'empty';
        html += `<div class="as-card">
            <div class="as-name">\\u{1F464} ${a.name}</div>
            <div class="as-loc">\\u{1F4CD} ${roomName}</div>
            <div class="as-inv">\\u{1F392} ${invStr}</div>
        </div>`;
    }
    strip.innerHTML = html;
}

// Progress bar
function updateProgressBar(chain) {
    if (chain && chain.length > 0) escapeChain = chain;
    if (escapeChain.length === 0) {
        document.getElementById('pb-label').textContent = 'Puzzle progress: 0/0 steps';
        document.getElementById('progress-fill').style.width = '0%';
        return;
    }
    const completed = escapeChain.filter(s => s.status === 'complete').length;
    const total = escapeChain.length;
    const pct = Math.round((completed / total) * 100);
    document.getElementById('pb-label').textContent = `Puzzle progress: ${completed}/${total} steps`;
    document.getElementById('progress-fill').style.width = pct + '%';
}

function updateFeedStatus(text, color) {
    document.getElementById('feed-status').textContent = text;
    document.getElementById('feed-status').style.color = color || '#3fb950';
}

// ================================================================
// DIRECTOR MODE: Card system
// ================================================================
function renderDirCard() {
    if (dirCardIdx < 0 || dirCardIdx >= dirCards.length) return;
    const c = dirCards[dirCardIdx];
    const card = document.getElementById('dir-current-card');
    const isFinished = c.finished;
    let html = `<div class="chapter-num">CHAPTER ${c.tick + 1}</div>`;
    html += `<div>${(c.narrative || 'No narration.').replace(/\\n/g, '<br>')}</div>`;
    if (c.events && c.events.length) {
        html += `<div class="card-events">${c.events.map(e => e.description).join(' | ')}</div>`;
    }
    card.innerHTML = html;
    card.className = 'story-card' + (isFinished ? ' finished' : '');
    updateDirNav();
}

function updateDirNav() {
    const total = dirCards.length;
    document.getElementById('dir-page-info').textContent = total > 0 ? `${dirCardIdx + 1} / ${total}` : '0 / 0';
    document.getElementById('dir-btn-prev').disabled = dirCardIdx <= 0;
    document.getElementById('dir-btn-next').disabled = dirCardIdx >= total - 1;
}

function dirPrevCard() {
    if (dirCardIdx > 0) { dirCardIdx--; dirAutoFollow = false; renderDirCard(); }
}
function dirNextCard() {
    if (dirCardIdx < dirCards.length - 1) {
        dirCardIdx++;
        if (dirCardIdx === dirCards.length - 1) dirAutoFollow = true;
        renderDirCard();
    }
}

// ================================================================
// SHARED: Button state, API calls
// ================================================================
function setButtonState(paused) {
    isPaused = paused;
    // Feed buttons
    const fp = document.getElementById('feed-btn-pause');
    const fr = document.getElementById('feed-btn-resume');
    const fs = document.getElementById('feed-btn-step');
    fp.disabled = paused; fr.disabled = !paused; fs.disabled = !paused;
    if (paused) fp.classList.remove('active'); else fp.classList.add('active');
    // Director buttons
    const dp = document.getElementById('dir-btn-pause');
    const dr = document.getElementById('dir-btn-resume');
    const ds = document.getElementById('dir-btn-step');
    dp.disabled = paused; dr.disabled = !paused; ds.disabled = !paused;
    if (paused) dp.classList.remove('active'); else dp.classList.add('active');
}

function updateAllStatus(text, color) {
    updateFeedStatus(text, color);
    document.getElementById('dir-status').textContent = text;
    document.getElementById('dir-status').style.color = color || '#3fb950';
}

function simPause() {
    fetch('/api/pause', {method:'POST'}).then(() => {
        setButtonState(true);
        updateAllStatus('Paused', '#e3b341');
    });
}
function simResume() {
    // If we're still on seed/reveal, jump to feed
    if (storyScreen !== 'feed') jumpToFeed();
    fetch('/api/resume', {method:'POST'}).then(() => {
        setButtonState(false);
        updateAllStatus('Running...', '#3fb950');
    });
}
function simStep() {
    if (storyScreen !== 'feed') jumpToFeed();
    updateAllStatus('Stepping...', '#58a6ff');
    fetch('/api/step', {method:'POST'}).then(() => {
        updateAllStatus('Paused (after step)', '#e3b341');
    });
}
function simSave() {
    fetch('/api/save', {method:'POST'}).then(r => r.json()).then(d => {
        updateAllStatus(`Saved: ${d.name} (id=${d.save_id})`, '#3fb950');
    });
}

let saveListOpen = false;
function toggleSaveList() {
    saveListOpen = !saveListOpen;
    // Feed save list
    const feedSL = document.getElementById('feed-save-list');
    // Director save list
    const dirSL = document.getElementById('dir-save-list');
    if (saveListOpen) {
        refreshSaveList();
        feedSL.style.display = 'block';
        dirSL.style.display = 'block';
    } else {
        feedSL.style.display = 'none';
        dirSL.style.display = 'none';
    }
}
function refreshSaveList() {
    fetch('/api/saves').then(r => r.json()).then(d => {
        const html = (!d.saves || d.saves.length === 0)
            ? '<div style="color:#8b949e">No saves yet</div>'
            : d.saves.map(s => `
                <div class="save-entry">
                    <div>
                        <span class="save-name">${s.name}</span>
                        <span class="save-info"> -- ${s.scenario} -- ${s.created_at.slice(0,19)}</span>
                    </div>
                    <div>
                        <button onclick="simLoad(${s.id})">Load</button>
                        <button class="del" onclick="simDelete(${s.id})">Del</button>
                    </div>
                </div>
            `).join('');
        document.getElementById('feed-save-content').innerHTML = html;
        document.getElementById('dir-save-list').innerHTML = html;
    });
}
function simLoad(saveId) {
    fetch('/api/load/' + saveId, {method:'POST'}).then(r => r.json()).then(d => {
        updateAllStatus(`Loaded: ${d.name} (tick ${d.tick})`, '#58a6ff');
        setButtonState(true);
        saveListOpen = false;
        document.getElementById('feed-save-list').style.display = 'none';
        document.getElementById('dir-save-list').style.display = 'none';
        if (storyScreen !== 'feed') jumpToFeed();
    });
}
function simDelete(saveId) {
    fetch('/api/saves/' + saveId, {method:'DELETE'}).then(() => refreshSaveList());
}
function simReset() {
    if (!confirm('Reset the game? All unsaved progress will be lost.')) return;
    fetch('/api/reset', {method:'POST'}).then(r => r.json()).then(d => {
        updateAllStatus(`Game reset (${d.scenario}) -- press Resume or Step`, '#e3b341');
        setButtonState(true);
        // Clear cards
        feedCards.length = 0; feedCardIdx = -1; feedAutoFollow = true;
        dirCards.length = 0; dirCardIdx = -1; dirAutoFollow = true;
        document.getElementById('feed-current-card').innerHTML = '<div class="fc-chapter">Waiting for first tick...</div>';
        document.getElementById('dir-current-card').innerHTML = '<div class="chapter-num">Waiting for first tick...</div>';
        updateFeedNav(); updateDirNav();
        document.getElementById('dir-events').innerHTML = '';
        escapeChain = [];
        updateProgressBar([]);
        updateTokenDisplay({total_tokens: 0}, null);
    });
}

// ================================================================
// TOKENS
// ================================================================
function updateTokenDisplay(usage, profile) {
    if (!usage) return;
    const fmt = n => n >= 1000 ? (n/1000).toFixed(1) + 'k' : n;
    const t = usage.total_tokens || 0;
    let breakdown = '';
    if (profile) {
        const totals = {decide: {i:0,o:0}, extract: {i:0,o:0}, reflect: {i:0,o:0}};
        for (const [aid, p] of Object.entries(profile)) {
            for (const ct of ['decide','extract','reflect']) {
                if (p[ct]) { totals[ct].i += p[ct].input; totals[ct].o += p[ct].output; }
            }
        }
        const parts = [];
        for (const [ct, v] of Object.entries(totals)) {
            const sum = v.i + v.o;
            if (sum > 0) parts.push(`${ct}:${fmt(v.i)}`);
        }
        if (parts.length) breakdown = ' [' + parts.join(' ') + ']';
    }
    const text = `Tokens: ${fmt(t)}${breakdown}`;
    document.getElementById('feed-token-display').textContent = text;
    document.getElementById('dir-token-display').textContent = text;
}

// ================================================================
// DIRECTOR: Map, Puzzles, Agents, Log
// ================================================================
const ROOM_PUZZLES = {
    'start':    'Clues: Note, Book',
    'workshop': 'Puzzles: Lock+Key, Combo Lock',
    'vault':    'Puzzles: Pressure Plate, Levers',
    'sanctum':  'Puzzles: Password, Brazier',
    'hallway':  'Exit: Iron Door',
    'library':  'Clues: Code Note, Hint Book',
    'lab':      'Puzzles: Lock Box, Trial',
};

function updateMap(ws_data) {
    if (!ws_data) return;
    const rooms = ws_data.rooms || {};
    const agents = ws_data.agents || {};
    const doors = ws_data.doors || {};

    const roomIds = Object.keys(rooms);
    const positions = autoLayout(roomIds, rooms, doors);

    const allX = Object.values(positions).map(p => p.x);
    const allY = Object.values(positions).map(p => p.y);
    const pad = 80;
    const minX = Math.min(...allX) - pad, maxX = Math.max(...allX) + pad;
    const minY = Math.min(...allY) - pad, maxY = Math.max(...allY) + pad;
    const w = maxX - minX, h = maxY - minY;

    const agentsByRoom = {};
    const agentList = Object.values(agents);
    for (const a of agentList) {
        if (!agentsByRoom[a.room_id]) agentsByRoom[a.room_id] = [];
        agentsByRoom[a.room_id].push(a);
    }

    let svg = `<svg viewBox="${minX - 10} ${minY - 10} ${w + 20} ${h + 20}" xmlns="http://www.w3.org/2000/svg">`;
    svg += `<defs>
        <marker id="arrow" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="8" markerHeight="6" orient="auto">
            <path d="M 0 0 L 10 3 L 0 6 z" fill="#484f58"/>
        </marker>
    </defs>`;

    const drawnDoors = new Set();
    for (const [rid, room] of Object.entries(rooms)) {
        const p1 = positions[rid];
        if (!p1) continue;
        for (const [dir, did] of Object.entries(room.doors || {})) {
            if (drawnDoors.has(did)) continue;
            drawnDoors.add(did);
            const door = doors[did];
            if (!door) continue;
            const otherRid = door.room_a === rid ? door.room_b : door.room_a;
            const p2 = positions[otherRid];
            if (!p2) continue;
            const locked = door.locked;
            const edgeColor = locked ? '#f85149' : '#3fb950';
            const dashArray = locked ? '6,4' : 'none';
            const lockIcon = locked ? '\\u{1F512}' : '\\u{1F513}';
            const dx = p2.x - p1.x, dy = p2.y - p1.y;
            const len = Math.sqrt(dx*dx + dy*dy) || 1;
            const nx = dx/len, ny = dy/len;
            const r = 40;
            const x1 = p1.x + nx*r, y1 = p1.y + ny*r;
            const x2 = p2.x - nx*r, y2 = p2.y - ny*r;
            const mx = (p1.x + p2.x)/2, my = (p1.y + p2.y)/2;
            svg += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${edgeColor}" stroke-width="2" stroke-dasharray="${dashArray}" opacity="0.7"/>`;
            svg += `<text x="${mx}" y="${my - 6}" text-anchor="middle" font-size="12" fill="${edgeColor}">${lockIcon}</text>`;
            svg += `<text x="${mx}" y="${my + 10}" text-anchor="middle" font-size="8" font-family="monospace" fill="#484f58">${door.name}</text>`;
        }
    }

    for (const [rid, room] of Object.entries(rooms)) {
        const p = positions[rid];
        if (!p) continue;
        const hasAgent = !!agentsByRoom[rid];
        const stroke = hasAgent ? '#58a6ff' : '#30363d';
        const fill = hasAgent ? '#161b22' : '#0d1117';
        svg += `<rect x="${p.x - 55}" y="${p.y - 30}" width="110" height="60" rx="8" fill="${fill}" stroke="${stroke}" stroke-width="${hasAgent ? 2 : 1}"/>`;
        svg += `<text x="${p.x}" y="${p.y - 12}" text-anchor="middle" font-size="11" font-weight="bold" font-family="monospace" fill="#e6edf3">${room.name}</text>`;
        const note = ROOM_PUZZLES[rid] || '';
        if (note) {
            svg += `<text x="${p.x}" y="${p.y + 3}" text-anchor="middle" font-size="8" font-family="monospace" fill="#8b949e">${note}</text>`;
        }
        const roomAgents = agentsByRoom[rid] || [];
        roomAgents.forEach((a, i) => {
            const color = AGENT_COLORS[agentList.indexOf(a) % AGENT_COLORS.length];
            const ax = p.x - 20 + i * 25;
            const ay = p.y + 18;
            svg += `<circle cx="${ax}" cy="${ay}" r="7" fill="${color}" opacity="0.9"/>`;
            svg += `<text x="${ax}" y="${ay + 3}" text-anchor="middle" font-size="7" font-weight="bold" fill="#0d1117">${a.name[0]}</text>`;
        });
    }
    svg += '</svg>';
    document.getElementById('dir-scene-graph').innerHTML = svg;
}

function autoLayout(roomIds, rooms, doors) {
    const pos = {};
    const n = roomIds.length;
    if (n === 0) return pos;
    const adj = {};
    for (const rid of roomIds) adj[rid] = new Set();
    for (const door of Object.values(doors)) {
        if (adj[door.room_a] && adj[door.room_b]) {
            adj[door.room_a].add(door.room_b);
            adj[door.room_b].add(door.room_a);
        }
    }
    const cx = n * 40, cy = n * 30;
    const radius = Math.max(80, n * 25);
    for (let i = 0; i < n; i++) {
        const angle = (2 * Math.PI * i) / n;
        pos[roomIds[i]] = { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) };
    }
    const repulsion = 8000;
    const attraction = 0.02;
    const idealDist = 160;
    for (let iter = 0; iter < 50; iter++) {
        const forces = {};
        for (const rid of roomIds) forces[rid] = { fx: 0, fy: 0 };
        for (let i = 0; i < n; i++) {
            for (let j = i + 1; j < n; j++) {
                const a = roomIds[i], b = roomIds[j];
                let dx = pos[a].x - pos[b].x;
                let dy = pos[a].y - pos[b].y;
                const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                const force = repulsion / (dist * dist);
                const fx = (dx / dist) * force;
                const fy = (dy / dist) * force;
                forces[a].fx += fx; forces[a].fy += fy;
                forces[b].fx -= fx; forces[b].fy -= fy;
            }
        }
        for (const rid of roomIds) {
            for (const neighbor of adj[rid]) {
                let dx = pos[neighbor].x - pos[rid].x;
                let dy = pos[neighbor].y - pos[rid].y;
                const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                const force = attraction * (dist - idealDist);
                forces[rid].fx += (dx / dist) * force;
                forces[rid].fy += (dy / dist) * force;
            }
        }
        const damping = 0.85 - iter * 0.01;
        for (const rid of roomIds) {
            pos[rid].x += forces[rid].fx * damping;
            pos[rid].y += forces[rid].fy * damping;
        }
    }
    let minX = Infinity, minY = Infinity;
    for (const rid of roomIds) {
        if (pos[rid].x < minX) minX = pos[rid].x;
        if (pos[rid].y < minY) minY = pos[rid].y;
    }
    for (const rid of roomIds) {
        pos[rid].x -= minX;
        pos[rid].y -= minY;
    }
    return pos;
}

function updateDirPuzzles(ws_data, chain) {
    if (chain && chain.length > 0) escapeChain = chain;
    const puzzleDiv = document.getElementById('dir-puzzle-list');
    if (escapeChain.length === 0) {
        puzzleDiv.innerHTML = '<div style="color:#8b949e">No escape chain (use Create to generate one)</div>';
        return;
    }
    const icons = {examine:'\\u{1F50D}', reveal:'\\u{2728}', solve:'\\u{1F9E9}', unlock:'\\u{1F513}', escape:'\\u{1F6AA}'};
    let html = '';
    const completed = escapeChain.filter(s => s.status === 'complete').length;
    const total = escapeChain.length;
    html += `<div style="color:#8b949e;font-size:10px;margin-bottom:6px;">${completed}/${total} steps complete</div>`;
    for (const step of escapeChain) {
        const icon = icons[step.action] || '\\u{2022}';
        const status = step.status === 'complete' ? 'solved' : 'locked';
        const statusText = step.status === 'complete' ? 'DONE' : 'PENDING';
        html += `<div class="puzzle-row">
            <span class="puzzle-icon">${icon}</span>
            <span class="puzzle-name" style="font-size:10px">${step.step}. ${step.description}</span>
            <span class="puzzle-status ${status}">${statusText}</span>
        </div>`;
    }
    puzzleDiv.innerHTML = html;
}

function updateDirAgents(ws_data) {
    if (!ws_data) return;
    const agents = ws_data.agents || {};
    const rooms = ws_data.rooms || {};
    let html = '';
    for (const a of Object.values(agents)) {
        const roomName = rooms[a.room_id] ? rooms[a.room_id].name : a.room_id;
        const inv = (a.inventory || []).map(i => i.name);
        const invStr = inv.length
            ? `<div class="agent-inv">\\u{1F392} ${inv.join(', ')}</div>`
            : `<div class="agent-inv-empty">\\u{1F392} empty</div>`;
        html += `<div class="agent-card">
            <div class="agent-name">\\u{1F464} ${a.name}</div>
            <div class="agent-location">\\u{1F4CD} ${roomName}</div>
            ${invStr}
        </div>`;
    }
    document.getElementById('dir-agent-list').innerHTML = html;
}

// Director log tabs
let activeLogTab = 'dir-events';
let logTimer = null;

function switchLogTab(tab, tabEl) {
    activeLogTab = tab;
    document.querySelectorAll('#dir-log-panel .log-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('#dir-log-panel .log-content').forEach(c => c.style.display = 'none');
    tabEl.classList.add('active');
    document.getElementById(tab).style.display = 'block';
    if (tab === 'dir-server-log') {
        refreshServerLog();
        if (!logTimer) logTimer = setInterval(refreshServerLog, 3000);
    } else {
        if (logTimer) { clearInterval(logTimer); logTimer = null; }
    }
}

function slColorize(line) {
    if (line.includes('TICK ') || line.includes('====')) return 'sl-tick';
    if (line.includes('->')) return 'sl-action';
    if (line.includes('??') || line.includes('>>') || line.includes('++') || line.includes('**') || line.includes("''") || line.includes('!!') || line.includes('XX')) return 'sl-event';
    if (line.includes('memory]')) return 'sl-memory';
    if (line.includes('TOKENS:')) return 'sl-token';
    if (line.includes('error') || line.includes('Error') || line.includes('GAME OVER')) return 'sl-error';
    return '';
}

function refreshServerLog() {
    fetch('/api/log?n=100').then(r => r.json()).then(d => {
        const el = document.getElementById('dir-server-log');
        el.innerHTML = d.lines.map(l => {
            const cls = slColorize(l);
            const escaped = l.replace(/</g, '&lt;').replace(/>/g, '&gt;');
            return cls ? `<span class="${cls}">${escaped}</span>` : escaped;
        }).join('\\n');
        el.scrollTop = el.scrollHeight;
    }).catch(() => {});
}

// Scene fullscreen
function toggleFullscreenScene() {
    const panel = document.getElementById('dir-map-panel');
    if (panel.style.position === 'fixed') {
        panel.style.position = '';
        panel.style.top = '';
        panel.style.left = '';
        panel.style.right = '';
        panel.style.bottom = '';
        panel.style.zIndex = '';
        panel.style.background = '';
        panel.style.padding = '';
        panel.style.overflow = '';
    } else {
        panel.style.position = 'fixed';
        panel.style.top = '0';
        panel.style.left = '0';
        panel.style.right = '0';
        panel.style.bottom = '0';
        panel.style.zIndex = '999';
        panel.style.background = '#0a0e14';
        panel.style.padding = '16px';
        panel.style.overflow = 'auto';
    }
}

// Copy scene
function copyScene() {
    const idx = currentMode === 'story' ? feedCardIdx : dirCardIdx;
    const cards = currentMode === 'story' ? feedCards : dirCards;
    if (idx < 0 || idx >= cards.length) return;
    const c = cards[idx];
    const parts = [];
    parts.push('IMAGE GENERATION PROMPT:');
    parts.push('Style: Dark atmospheric digital painting, escape room horror, dramatic lighting');
    parts.push('');
    parts.push('Scene: ' + (c.narrative || 'No narration'));
    parts.push('');
    if (c.agents) {
        for (const a of Object.values(c.agents)) {
            const room = c.rooms && c.rooms[a.room_id] ? c.rooms[a.room_id].name : a.room_id;
            const inv = (a.inventory || []).map(i => i.name).join(', ') || 'nothing';
            parts.push(`Character: ${a.name} (${a.description}) in ${room}, carrying ${inv}`);
        }
    }
    if (c.rooms) {
        for (const r of Object.values(c.rooms)) {
            parts.push(`Location: ${r.name} - ${r.description}`);
        }
    }
    if (c.events && c.events.length) {
        parts.push('');
        parts.push('Actions: ' + c.events.map(e => e.description).join('. '));
    }
    const text = parts.join('\\n');
    navigator.clipboard.writeText(text).then(() => {
        const toast = document.getElementById('copy-toast');
        toast.style.display = 'block';
        setTimeout(() => { toast.style.display = 'none'; }, 2000);
    });
}

// ================================================================
// DIRECTOR: Map Creator (Reverse Architect)
// ================================================================
const ENDING_BADGES = {
    good: {icon:'\\u{1F3C6}', label:'Good', color:'#22c55e'},
    bad: {icon:'\\u{1F480}', label:'Bad', color:'#ef4444'},
    secret: {icon:'\\u{1F31F}', label:'Secret', color:'#f59e0b'},
    true_: {icon:'\\u{1F52E}', label:'True', color:'#a855f7'},
};

let lastPreviewData = null;

function toggleCreator() {
    const o = document.getElementById('creator-overlay');
    o.style.display = o.style.display === 'none' ? 'block' : 'none';
    if (o.style.display === 'block') loadPresets();
}

function loadPresets() {
    fetch('/api/presets').then(r=>r.json()).then(d => {
        const div = document.getElementById('preset-buttons');
        div.innerHTML = Object.entries(d.presets).map(([k,v]) =>
            `<button onclick="selectPreset('${k}')" style="background:#21262d;border:1px solid #30363d;color:#c9d1d9;border-radius:4px;padding:3px 8px;cursor:pointer;font-family:monospace;font-size:10px;">${v.builder.split(' ').pop()} (${v.difficulty})</button>`
        ).join('');
    });
    updateEndingPreview();
}

function selectPreset(name) {
    fetch('/api/presets').then(r=>r.json()).then(d => {
        const p = d.presets[name];
        if (!p) return;
        document.getElementById('arc-builder').value = p.builder;
        document.getElementById('arc-goal').value = p.goal;
        document.getElementById('arc-background').value = p.background;
        document.getElementById('arc-difficulty').value = p.difficulty;
        updateEndingPreview();
        document.getElementById('creator-status').textContent = `Loaded preset: ${name}`;
        document.getElementById('creator-status').style.color = '#3fb950';
    });
}

function updateEndingPreview() {
    const diff = parseInt(document.getElementById('arc-difficulty').value);
    const endings = ['good','bad'];
    if (diff >= 3) endings.push('secret');
    if (diff >= 4) endings.push('true_');
    const div = document.getElementById('ending-preview');
    div.innerHTML = endings.map(e => {
        const b = ENDING_BADGES[e];
        return `<span style="background:${b.color}22;color:${b.color};border:1px solid ${b.color}44;border-radius:3px;padding:1px 6px;font-size:10px;font-family:monospace;">${b.icon} ${b.label}</span>`;
    }).join('');
}

function getStoryInput() {
    return {
        builder: document.getElementById('arc-builder').value.trim() || 'Mystery Builder',
        goal: document.getElementById('arc-goal').value.trim() || 'Hidden Treasure',
        background: document.getElementById('arc-background').value.trim() || 'A mysterious place',
        difficulty: parseInt(document.getElementById('arc-difficulty').value),
    };
}

function previewMap() {
    const story = getStoryInput();
    const statusEl = document.getElementById('creator-status');
    statusEl.textContent = 'Generating preview...';
    statusEl.style.color = '#58a6ff';
    fetch('/api/preview-architect', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(story),
    }).then(r=>r.json()).then(d => {
        if (d.error) {
            statusEl.textContent = 'Error: ' + d.error;
            statusEl.style.color = '#f85149';
            return;
        }
        lastPreviewData = d;
        showPreview(d);
        statusEl.textContent = `Preview: ${d.stats.total_nodes} puzzles, ${d.stats.endings} endings, ${d.stats.forks} forks`;
        statusEl.style.color = '#3fb950';
        document.getElementById('btn-preview').style.display = 'none';
        document.getElementById('btn-regenerate').style.display = 'block';
        document.getElementById('btn-play-map').style.display = 'block';
    }).catch(e => {
        statusEl.textContent = 'Error: ' + e;
        statusEl.style.color = '#f85149';
    });
}

function showPreview(data) {
    const container = document.getElementById('preview-container');
    container.style.display = 'block';
    const s = data.stats;
    document.getElementById('preview-stats').innerHTML =
        `<span style="color:#58a6ff;font-family:monospace;font-size:11px;">${s.total_nodes} nodes</span>` +
        `<span style="color:#3fb950;font-family:monospace;font-size:11px;">${s.total_edges} edges</span>` +
        `<span style="color:#e3b341;font-family:monospace;font-size:11px;">${s.endings} endings</span>` +
        `<span style="color:#d2a8ff;font-family:monospace;font-size:11px;">${s.forks} forks</span>` +
        `<span style="color:#8b949e;font-family:monospace;font-size:11px;">${s.entrances} entrances</span>`;
    document.getElementById('preview-endings').innerHTML = data.endings.map(e => {
        const b = ENDING_BADGES[e.key] || {icon:'?',color:'#8b949e'};
        return `<div style="display:inline-flex;align-items:center;gap:4px;margin-right:10px;font-family:monospace;font-size:11px;">` +
            `<span style="color:${b.color}">${b.icon} ${e.label}</span>` +
            `<span style="color:#8b949e">(${e.chain_length} steps)</span></div>`;
    }).join('');
    renderPreviewGraph(data.nodes, data.edges);
}

function renderPreviewGraph(nodes, edges) {
    if (!nodes.length) return;
    const xs = nodes.map(n=>n.x), ys = nodes.map(n=>n.y);
    const minX = Math.min(...xs)-40, maxX = Math.max(...xs)+40;
    const minY = Math.min(...ys)-40, maxY = Math.max(...ys)+40;
    const w = maxX-minX, h = maxY-minY;
    let svg = `<svg viewBox="${minX} ${minY} ${w} ${h}" style="width:100%;height:auto;max-height:250px;">`;
    for (const e of edges) {
        const from = nodes.find(n=>n.id===e.from);
        const to = nodes.find(n=>n.id===e.to);
        if (!from || !to) continue;
        const color = e.color || '#30363d';
        const dash = e.is_branch ? '6,3' : '4,3';
        const sw = e.is_branch ? 2.5 : 1.5;
        svg += `<line x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}" stroke="${color}" stroke-width="${sw}" stroke-dasharray="${dash}" opacity="0.6"/>`;
    }
    const typeIcons = {lock:'\\u{1F512}',cipher:'\\u{1F522}',hidden:'\\u{1F50D}',mechanism:'\\u{2699}',riddle:'\\u{1F4AC}',trap:'\\u{26A0}',key:'\\u{1F511}'};
    for (const n of nodes) {
        const r = n.is_goal ? 18 : n.is_fork ? 14 : n.is_entrance ? 12 : 10;
        const fill = n.path_color || '#30363d';
        const stroke = n.is_goal ? '#fff' : n.is_entrance ? '#3fb950' : 'none';
        svg += `<circle cx="${n.x}" cy="${n.y}" r="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${stroke!=='none'?2:0}" opacity="0.8"/>`;
        const icon = n.is_goal ? (ENDING_BADGES[n.ending_type]||{}).icon||'\\u{2B50}' : n.is_fork ? '\\u{1F500}' : typeIcons[n.type] || '\\u{2022}';
        svg += `<text x="${n.x}" y="${n.y+4}" text-anchor="middle" font-size="${r*0.9}" fill="#fff">${icon}</text>`;
        if (n.is_entrance) svg += `<text x="${n.x}" y="${n.y-r-4}" text-anchor="middle" font-size="8" fill="#3fb950">START</text>`;
    }
    svg += '</svg>';
    document.getElementById('preview-graph').innerHTML = svg;
}

function playPreviewedMap() {
    if (!lastPreviewData) return;
    const story = lastPreviewData.story;
    const statusEl = document.getElementById('creator-status');
    statusEl.textContent = 'Building playable world...';
    statusEl.style.color = '#58a6ff';
    fetch('/api/generate-architect', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(story),
    }).then(r=>r.json()).then(d => {
        if (d.error) {
            statusEl.textContent = 'Error: ' + d.error;
            statusEl.style.color = '#f85149';
            return;
        }
        statusEl.textContent = `Loaded! ${d.rooms}R ${d.doors}D ${d.endings} endings -- press Resume`;
        statusEl.style.color = '#3fb950';
        feedCards.length = 0; feedCardIdx = -1; feedAutoFollow = true;
        dirCards.length = 0; dirCardIdx = -1; dirAutoFollow = true;
        document.getElementById('feed-current-card').innerHTML = '<div class="fc-chapter">Map loaded -- press Resume to play!</div>';
        document.getElementById('dir-current-card').innerHTML = '<div class="chapter-num">Map loaded -- press Resume to play!</div>';
        updateFeedNav(); updateDirNav();
        document.getElementById('dir-events').innerHTML = '';
        updateTokenDisplay({total_tokens: 0}, null);
        escapeChain = [];
        updateProgressBar([]);
        setButtonState(true);
        updateAllStatus('New map ready -- press Resume or Step', '#e3b341');
        if (storyScreen !== 'feed') jumpToFeed();
        setTimeout(() => { document.getElementById('creator-overlay').style.display = 'none'; }, 1500);
    });
}

// ================================================================
// KEYBOARD NAVIGATION
// ================================================================
document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') {
        if (currentMode === 'story') feedPrevCard();
        else dirPrevCard();
    } else if (e.key === 'ArrowRight') {
        if (currentMode === 'story') feedNextCard();
        else dirNextCard();
    }
});

// ================================================================
// WEBSOCKET
// ================================================================
const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
const ws = new WebSocket(`${proto}//${location.host}/ws`);

ws.onopen = () => {
    updateAllStatus('Paused -- press Resume or Step to begin', '#e3b341');
    setButtonState(true);
};

ws.onclose = () => {
    updateAllStatus('Disconnected -- refresh to reconnect.', '#f85149');
    // Disable all buttons
    ['feed-btn-pause','feed-btn-resume','feed-btn-step',
     'dir-btn-pause','dir-btn-resume','dir-btn-step'].forEach(id => {
        document.getElementById(id).disabled = true;
    });
    setTimeout(() => { location.reload(); }, 5000);
};

ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);

    if (msg.type === 'tick' || msg.type === 'snapshot') {
        if (msg.world_state) {
            // Director panels
            updateMap(msg.world_state);
            updateDirPuzzles(msg.world_state, msg.escape_chain);
            updateDirAgents(msg.world_state);
            // Story mode panels
            updateAgentStrip(msg.world_state);
            updateProgressBar(msg.escape_chain);

            // If we're on the reveal screen, populate rooms
            if (storyScreen === 'seed' || document.getElementById('reveal-screen').style.display === 'flex') {
                pendingSnapshot = msg.world_state;
                if (document.getElementById('reveal-screen').style.display === 'flex') {
                    populateRevealRooms(msg.world_state);
                }
            }
        }
        if (msg.token_usage) {
            updateTokenDisplay(msg.token_usage, msg.token_profile);
        }
        if (msg.type === 'snapshot' && msg.paused !== undefined) {
            setButtonState(msg.paused);
            if (msg.paused) {
                updateAllStatus(`Paused at tick ${msg.tick} -- press Resume or Step`, '#e3b341');
            }
            // If snapshot has ticks, we have an existing game: jump to feed
            if (msg.tick > 0 && storyScreen === 'seed') {
                jumpToFeed();
            }
        }
    }

    if (msg.type === 'tick') {
        addFeedCard({
            tick: msg.tick,
            narrative: msg.narrative || '',
            events: msg.events || [],
            agents: msg.world_state ? msg.world_state.agents : {},
            rooms: msg.world_state ? msg.world_state.rooms : {},
            finished: false,
        });
        // Director event log
        const eventsDiv = document.getElementById('dir-events');
        const group = document.createElement('div');
        group.className = 'tick-group';
        group.innerHTML = `<div class="tick-label">Tick ${msg.tick}</div>`;
        msg.events.forEach(ev => {
            const div = document.createElement('div');
            div.className = `event ${ev.type}`;
            div.textContent = ev.description;
            group.appendChild(div);
        });
        eventsDiv.appendChild(group);
        eventsDiv.scrollTop = eventsDiv.scrollHeight;

        // If still on seed/reveal, jump to feed
        if (storyScreen !== 'feed') jumpToFeed();
    } else if (msg.type === 'processing') {
        updateAllStatus(msg.message || 'Processing...', '#58a6ff');
    } else if (msg.type === 'paused') {
        setButtonState(true);
        updateAllStatus(`Paused at tick ${msg.tick}`, '#e3b341');
    } else if (msg.type === 'finished' || msg.type === 'finished_idle') {
        addFeedCard({
            tick: msg.tick || feedCards.length,
            narrative: msg.narrative || msg.reason,
            events: [],
            agents: {},
            rooms: {},
            finished: true,
        });
        const eventsDiv = document.getElementById('dir-events');
        const div = document.createElement('div');
        div.className = 'event state_change';
        div.style.fontWeight = 'bold';
        div.textContent = msg.reason || 'Simulation complete';
        eventsDiv.appendChild(div);

        ['feed-btn-pause','feed-btn-resume','feed-btn-step',
         'dir-btn-pause','dir-btn-resume','dir-btn-step'].forEach(id => {
            document.getElementById(id).disabled = true;
        });
        updateAllStatus('Simulation complete', '#3fb950');
    }
};

// ================================================================
// INIT
// ================================================================
loadThemes();
</script>
</body>
</html>
"""

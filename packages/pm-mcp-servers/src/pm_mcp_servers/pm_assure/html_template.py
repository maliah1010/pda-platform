"""Self-contained HTML dashboard generator.

Produces a single .html file that works offline, with:
- Tailwind CSS via CDN
- Chart.js via CDN for trend charts
- Inter font via Google Fonts
- All data embedded as JSON
- TortoiseAI branded header/footer with Ant Newman attribution
- SVG gauge, KPI cards, OPAL module grid, trend chart, domain card, risk indicators
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def _health_colour(health: str) -> str:
    return {
        "HEALTHY": "#16a34a",
        "ATTENTION_NEEDED": "#d97706",
        "AT_RISK": "#ea580c",
        "CRITICAL": "#dc2626",
    }.get(health, "#64748b")


def _health_score(health: str) -> int:
    return {"HEALTHY": 90, "ATTENTION_NEEDED": 65, "AT_RISK": 40, "CRITICAL": 20}.get(health, 50)


def _domain_colour(domain: str) -> str:
    return {
        "CLEAR": "#16a34a",
        "COMPLICATED": "#1d4ed8",
        "COMPLEX": "#d97706",
        "CHAOTIC": "#dc2626",
    }.get(domain, "#64748b")


def _domain_bg(domain: str) -> str:
    return {
        "CLEAR": "#dcfce7",
        "COMPLICATED": "#dbeafe",
        "COMPLEX": "#fef3c7",
        "CHAOTIC": "#fee2e2",
    }.get(domain, "#f1f5f9")


def render_html(data: dict[str, Any]) -> str:
    """Render a complete self-contained HTML dashboard.

    Args:
        data: Dict with keys matching the export_dashboard_data panel structure,
              plus metadata fields: project_name, department, domain, project_id,
              generated_at.
    """
    project_name = data.get("project_name", "Unknown Project")
    department = data.get("department", "")
    domain = data.get("domain", "UNKNOWN")
    project_id = data.get("project_id", "")
    generated_at = data.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M"))
    key_risks = data.get("key_risks", [])

    # Panel data
    health_val = data.get("overall_health", {}).get("value", 50)
    health_str = (
        "HEALTHY" if health_val >= 75 else
        "ATTENTION_NEEDED" if health_val >= 50 else
        "AT_RISK" if health_val >= 25 else
        "CRITICAL"
    )
    domain_val = data.get("domain_classification", {}).get("value", domain)
    review_days = data.get("review_urgency", {}).get("value", 42)
    compliance = data.get("compliance_score", {}).get("value", 0)
    action_closure = data.get("action_closure", {}).get("value", 0)
    ai_confidence = data.get("ai_confidence", {}).get("value", 0)
    artefact_currency = data.get("artefact_currency", {}).get("value", 0)

    compliance_rows = data.get("compliance_trend", {}).get("rows", [])
    confidence_rows = data.get("confidence_trend", {}).get("rows", [])
    actions_rows = data.get("open_actions_table", {}).get("rows", [])
    artefact_rows = data.get("artefact_status_bar", {}).get("rows", [])

    # Trend chart data
    trend_labels = json.dumps([r.get("label", "") for r in compliance_rows])
    trend_scores = json.dumps([r.get("compliance_score", 0) for r in compliance_rows])
    conf_labels = json.dumps([r.get("label", "") for r in confidence_rows])
    conf_scores = json.dumps([r.get("confidence_score", 0) for r in confidence_rows])

    # Gauge SVG parameters
    gauge_pct = max(0, min(100, health_val)) / 100
    gauge_colour = _health_colour(health_str)

    # Actions table HTML
    actions_html = ""
    for r in actions_rows[:8]:
        status = r.get("assurance.action_status", "OPEN")
        status_colour = {
            "OPEN": "bg-amber-100 text-amber-800",
            "IN_PROGRESS": "bg-blue-100 text-blue-800",
            "CLOSED": "bg-green-100 text-green-800",
            "RECURRING": "bg-red-100 text-red-800",
        }.get(status, "bg-gray-100 text-gray-800")
        actions_html += f"""
        <tr class="border-b border-slate-100">
          <td class="py-2 px-3 text-xs font-mono text-slate-500">{r.get("assurance.action_id", "")}</td>
          <td class="py-2 px-3 text-sm text-slate-700">{r.get("assurance.action_text", "")}</td>
          <td class="py-2 px-3"><span class="text-xs px-2 py-0.5 rounded-full font-medium {status_colour}">{status}</span></td>
          <td class="py-2 px-3 text-xs text-slate-500">{r.get("assurance.action_owner", "")}</td>
        </tr>"""

    # Key risks HTML
    risks_html = ""
    for risk in key_risks[:5]:
        risks_html += f'<span class="inline-block bg-white/10 text-white text-xs px-2.5 py-1 rounded-full mr-2 mb-2">{risk}</span>'

    year = datetime.now().year

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{project_name} — PDA Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script>
    tailwind.config = {{
      theme: {{
        extend: {{
          fontFamily: {{ sans: ['Inter', 'system-ui', 'sans-serif'] }},
          colors: {{
            brand: {{ primary: '#D946EF', secondary: '#334155', accent: '#10B981' }},
            gov: {{ navy: '#0b1f4b', teal: '#0d9488' }},
          }}
        }}
      }}
    }}
  </script>
  <style>
    @media print {{
      .no-print {{ display: none !important; }}
      body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    }}
  </style>
</head>
<body class="bg-slate-50 font-sans">

  <!-- ========== HEADER ========== -->
  <header class="bg-brand-secondary px-6 py-3 flex items-center justify-between">
    <div class="flex items-center gap-3">
      <div class="w-8 h-8 rounded-lg bg-brand-primary flex items-center justify-center">
        <span class="text-white font-bold text-lg">T</span>
      </div>
      <div>
        <h1 class="text-white font-bold text-lg leading-tight">TortoiseAI</h1>
        <p class="text-slate-400 text-xs">OPAL &middot; Open Project Assurance Library</p>
      </div>
    </div>
    <div class="flex items-center gap-3">
      <span class="text-xs px-2.5 py-1 rounded-full font-medium" style="background: rgba(16,185,129,0.12); color: #10B981;">
        Powered by UDS v0.1.0
      </span>
      <span class="text-slate-400 text-xs no-print">Generated {generated_at}</span>
    </div>
  </header>

  <main class="max-w-7xl mx-auto px-6 py-6 space-y-6">

    <!-- ========== PROJECT HEADER ========== -->
    <div class="bg-gov-navy rounded-2xl p-6 text-white">
      <div class="flex items-start justify-between">
        <div>
          <div class="flex items-center gap-3 mb-2">
            <span class="px-3 py-1 rounded-full text-xs font-bold" style="background: {_domain_bg(domain)}; color: {_domain_colour(domain)};">
              {domain_val}
            </span>
            <span class="text-slate-400 text-xs font-mono">{project_id}</span>
          </div>
          <h2 class="text-2xl font-bold">{project_name}</h2>
          <p class="text-slate-300 text-sm mt-1">{department}</p>
        </div>
      </div>
      {f'<div class="mt-4">{risks_html}</div>' if risks_html else ''}
    </div>

    <!-- ========== KEY METRICS ROW ========== -->
    <div class="grid grid-cols-4 gap-4">
      <!-- Health Gauge -->
      <div class="bg-white rounded-2xl border border-slate-200 p-5 flex flex-col items-center">
        <p class="text-xs font-medium text-slate-500 uppercase tracking-wider mb-3">Assurance Health</p>
        <svg viewBox="0 0 120 70" class="w-28">
          <path d="M 10 60 A 50 50 0 0 1 110 60" fill="none" stroke="#e2e8f0" stroke-width="10" stroke-linecap="round"/>
          <path d="M 10 60 A 50 50 0 0 1 110 60" fill="none" stroke="{gauge_colour}" stroke-width="10" stroke-linecap="round"
                stroke-dasharray="{157 * gauge_pct} {157 * (1 - gauge_pct)}" />
          <text x="60" y="55" text-anchor="middle" class="text-2xl font-bold" fill="{gauge_colour}" font-size="22" font-family="Inter">{health_val}</text>
          <text x="60" y="68" text-anchor="middle" fill="#94a3b8" font-size="8" font-family="Inter">{health_str.replace('_', ' ')}</text>
        </svg>
      </div>

      <!-- Compliance -->
      <div class="bg-white rounded-2xl border border-slate-200 p-5">
        <p class="text-xs font-medium text-slate-500 uppercase tracking-wider">NISTA Compliance</p>
        <p class="text-3xl font-bold mt-2" style="color: {'#16a34a' if (compliance or 0) >= 80 else '#d97706' if (compliance or 0) >= 65 else '#dc2626'}">
          {compliance if compliance else 'N/A'}{'%' if compliance else ''}
        </p>
        <p class="text-xs text-slate-400 mt-1">OPAL-2 longitudinal score</p>
      </div>

      <!-- Action Closure -->
      <div class="bg-white rounded-2xl border border-slate-200 p-5">
        <p class="text-xs font-medium text-slate-500 uppercase tracking-wider">Action Closure</p>
        <p class="text-3xl font-bold mt-2" style="color: {'#16a34a' if action_closure >= 0.7 else '#d97706' if action_closure >= 0.4 else '#dc2626'}">
          {round(action_closure * 100)}%
        </p>
        <p class="text-xs text-slate-400 mt-1">OPAL-3 closed / total</p>
      </div>

      <!-- Next Review -->
      <div class="bg-white rounded-2xl border border-slate-200 p-5">
        <p class="text-xs font-medium text-slate-500 uppercase tracking-wider">Next Review</p>
        <p class="text-3xl font-bold mt-2" style="color: {'#dc2626' if review_days <= 7 else '#d97706' if review_days <= 14 else '#16a34a'}">
          {review_days} <span class="text-lg font-normal text-slate-400">days</span>
        </p>
        <p class="text-xs text-slate-400 mt-1">OPAL-5 adaptive scheduling</p>
      </div>
    </div>

    <!-- ========== CHARTS ROW ========== -->
    <div class="grid grid-cols-2 gap-6">
      <div class="bg-white rounded-2xl border border-slate-200 p-6">
        <h3 class="font-semibold text-slate-800 mb-4">Compliance Score Trend</h3>
        <canvas id="complianceChart" height="160"></canvas>
      </div>
      <div class="bg-white rounded-2xl border border-slate-200 p-6">
        <h3 class="font-semibold text-slate-800 mb-4">AI Confidence History</h3>
        <canvas id="confidenceChart" height="160"></canvas>
      </div>
    </div>

    <!-- ========== ARTEFACT STATUS + DOMAIN ========== -->
    <div class="grid grid-cols-2 gap-6">
      <!-- Artefact Status -->
      <div class="bg-white rounded-2xl border border-slate-200 p-6">
        <h3 class="font-semibold text-slate-800 mb-4">Artefact Currency (OPAL-1)</h3>
        <div class="space-y-3">
          {''.join(f'''
          <div class="flex items-center justify-between">
            <span class="text-sm text-slate-600">{r.get("assurance.currency_status", "")}</span>
            <div class="flex items-center gap-2">
              <div class="w-32 h-2 bg-slate-100 rounded-full overflow-hidden">
                <div class="h-full rounded-full" style="width: {min(100, r.get("assurance.artefact_count", 0) * 8.3)}%; background: {'#16a34a' if r.get("assurance.currency_status") == 'CURRENT' else '#d97706' if r.get("assurance.currency_status") == 'OUTDATED' else '#dc2626'};"></div>
              </div>
              <span class="text-sm font-semibold text-slate-700 w-6 text-right">{r.get("assurance.artefact_count", 0)}</span>
            </div>
          </div>
          ''' for r in artefact_rows)}
        </div>
      </div>

      <!-- Domain Classification -->
      <div class="rounded-2xl border-2 p-6" style="background: {_domain_bg(domain)}; border-color: {_domain_colour(domain)}40;">
        <h3 class="font-semibold text-slate-800 mb-2">Domain Classification (OPAL-10)</h3>
        <p class="text-4xl font-bold mb-2" style="color: {_domain_colour(domain)};">{domain_val}</p>
        <p class="text-sm text-slate-600 mb-3">Cynefin complexity domain based on 7 indicators</p>
        <div class="grid grid-cols-2 gap-2 text-xs">
          <div class="flex justify-between"><span class="text-slate-500">AI Confidence</span><span class="font-semibold">{round(ai_confidence * 100 if isinstance(ai_confidence, float) and ai_confidence <= 1 else ai_confidence)}%</span></div>
          <div class="flex justify-between"><span class="text-slate-500">Artefact Currency</span><span class="font-semibold">{round(artefact_currency * 100 if isinstance(artefact_currency, float) and artefact_currency <= 1 else artefact_currency)}%</span></div>
        </div>
      </div>
    </div>

    <!-- ========== OPEN ACTIONS TABLE ========== -->
    <div class="bg-white rounded-2xl border border-slate-200 p-6">
      <h3 class="font-semibold text-slate-800 mb-4">Open Actions (OPAL-3)</h3>
      <table class="w-full">
        <thead>
          <tr class="border-b border-slate-200">
            <th class="text-left py-2 px-3 text-xs font-semibold text-slate-500 uppercase">ID</th>
            <th class="text-left py-2 px-3 text-xs font-semibold text-slate-500 uppercase">Action</th>
            <th class="text-left py-2 px-3 text-xs font-semibold text-slate-500 uppercase">Status</th>
            <th class="text-left py-2 px-3 text-xs font-semibold text-slate-500 uppercase">Owner</th>
          </tr>
        </thead>
        <tbody>{actions_html}</tbody>
      </table>
    </div>

  </main>

  <!-- ========== FOOTER ========== -->
  <footer class="bg-brand-secondary px-6 py-6 mt-8">
    <div class="max-w-7xl mx-auto flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-lg bg-brand-primary flex items-center justify-center">
          <span class="text-white font-bold text-lg">T</span>
        </div>
        <div>
          <p class="text-white font-semibold text-sm">TortoiseAI</p>
          <p class="text-slate-400 text-xs">Production-ready AI for high-stakes environments</p>
        </div>
      </div>
      <div class="text-right">
        <p class="text-slate-300 text-xs">
          Built by Ant Newman &middot;
          <a href="https://tortoiseai.co.uk" class="hover:text-white" target="_blank" rel="noopener">tortoiseai.co.uk</a>
        </p>
        <p class="text-slate-500 text-xs mt-1">
          &copy; {year} Tortoise AI Ltd &middot;
          <a href="https://github.com/Tortoise-AI/uds" class="hover:text-slate-300" target="_blank" rel="noopener">UDS Specification</a>
          &middot;
          <a href="https://github.com/Tortoise-AI/pda-platform" class="hover:text-slate-300" target="_blank" rel="noopener">PDA Platform</a>
        </p>
      </div>
    </div>
  </footer>

  <!-- ========== CHART.JS INIT ========== -->
  <script>
    const complianceCtx = document.getElementById('complianceChart').getContext('2d');
    new Chart(complianceCtx, {{
      type: 'line',
      data: {{
        labels: {trend_labels},
        datasets: [{{
          label: 'Compliance %',
          data: {trend_scores},
          borderColor: '#D946EF',
          backgroundColor: 'rgba(217,70,239,0.08)',
          fill: true,
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 3,
          pointBackgroundColor: '#D946EF',
        }}]
      }},
      options: {{
        responsive: true,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
          y: {{ min: 0, max: 100, grid: {{ color: '#f1f5f9' }} }},
          x: {{ grid: {{ display: false }} }}
        }}
      }}
    }});

    const confCtx = document.getElementById('confidenceChart').getContext('2d');
    new Chart(confCtx, {{
      type: 'line',
      data: {{
        labels: {conf_labels},
        datasets: [{{
          label: 'Confidence',
          data: {conf_scores},
          borderColor: '#10B981',
          backgroundColor: 'rgba(16,185,129,0.08)',
          fill: true,
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 3,
          pointBackgroundColor: '#10B981',
        }}]
      }},
      options: {{
        responsive: true,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
          y: {{ min: 0, max: 1, grid: {{ color: '#f1f5f9' }} }},
          x: {{ grid: {{ display: false }} }}
        }}
      }}
    }});
  </script>

</body>
</html>"""

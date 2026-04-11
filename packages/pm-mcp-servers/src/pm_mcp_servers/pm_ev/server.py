"""PM-EV MCP server — Earned Value reporting tools.

Tools:
  1. compute_ev_metrics    — Compute full EV metrics (BCWS, BCWP, ACWP, SPI, CPI,
                             SV, CV, EAC, ETC, VAC, TCPI) from task schedule data.
  2. generate_ev_dashboard — Produce a self-contained HTML dashboard (no CDN
                             dependencies) visualising EV metrics and S-curve.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from mcp.types import TextContent, Tool

from pm_mcp_servers.shared import project_store

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

EV_TOOLS: list[Tool] = [
    Tool(
        name="compute_ev_metrics",
        description=(
            "Compute Earned Value metrics (BCWS, BCWP, ACWP, SPI, CPI, SV, CV, "
            "EAC, ETC, VAC, TCPI) from project task data. Requires the project to "
            "have been loaded first via load_project. Returns all metrics as JSON "
            "with interpretation strings."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project identifier returned by load_project.",
                },
                "status_date": {
                    "type": "string",
                    "description": (
                        "Data date in ISO 8601 format (YYYY-MM-DD). Defaults to "
                        "today if not supplied."
                    ),
                },
            },
            "required": ["project_id"],
        },
    ),
    Tool(
        name="generate_ev_dashboard",
        description=(
            "Generate a self-contained HTML Earned Value dashboard (no external "
            "dependencies) showing EV metrics, performance indices with traffic-light "
            "colour coding, and an S-curve chart rendered as inline SVG. "
            "Optionally writes to a file path; otherwise returns HTML as text."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project identifier returned by load_project.",
                },
                "status_date": {
                    "type": "string",
                    "description": (
                        "Data date in ISO 8601 format (YYYY-MM-DD). Defaults to "
                        "today if not supplied."
                    ),
                },
                "output_path": {
                    "type": "string",
                    "description": (
                        "Optional file path to write the HTML. If omitted the HTML "
                        "is returned as text content."
                    ),
                },
            },
            "required": ["project_id"],
        },
    ),
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_date(value: Any) -> date | None:
    """Safely coerce a date/datetime/string to a date object."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return None


def _fmt_currency(value: float, symbol: str) -> str:
    """Format a monetary value with thousands separator."""
    if abs(value) >= 1_000_000:
        return f"{symbol}{value / 1_000_000:,.2f}m"
    if abs(value) >= 1_000:
        return f"{symbol}{value:,.0f}"
    return f"{symbol}{value:,.2f}"


def _spi_colour(spi: float) -> str:
    if spi >= 0.95:
        return "#16a34a"
    if spi >= 0.80:
        return "#d97706"
    return "#dc2626"


def _cpi_colour(cpi: float) -> str:
    return _spi_colour(cpi)


def _overall_status(spi: float, cpi: float) -> tuple[str, str]:
    """Return (label, hex_colour) for the overall status badge."""
    if spi >= 0.95 and cpi >= 0.95:
        return "GREEN", "#16a34a"
    if spi >= 0.80 and cpi >= 0.80:
        return "AMBER", "#d97706"
    return "RED", "#dc2626"


def _interpret_spi(spi: float) -> str:
    if spi >= 0.95:
        return "On schedule"
    if spi >= 0.80:
        return "Slightly behind schedule"
    return "Behind schedule"


def _interpret_cpi(cpi: float) -> str:
    if cpi >= 0.95:
        return "Within budget"
    if cpi >= 0.80:
        return "Slightly over budget"
    return "Over budget"


# ---------------------------------------------------------------------------
# EV computation
# ---------------------------------------------------------------------------


def _compute_metrics(project: Any, status_date: date) -> dict[str, Any]:
    """
    Derive EV metrics from a pm_data_tools Project object.

    Returns a dict with keys: bcws, bcwp, acwp, bac, spi, cpi, sv, cv,
    eac, etc_, vac, tcpi, has_cost_data, currency, warnings, tasks_analysed.
    """
    tasks = getattr(project, "tasks", None) or []
    currency_symbol = getattr(project, "currency", None) or "£"
    warnings: list[str] = []

    bcws = 0.0
    bcwp = 0.0
    acwp_total = 0.0
    bac = 0.0
    has_cost_data = False
    tasks_analysed = 0

    for task in tasks:
        # Skip summary tasks / milestones that have no duration
        finish_raw = getattr(task, "finish_date", None) or getattr(task, "baseline_finish", None)
        start_raw = getattr(task, "start_date", None)
        finish = _parse_date(finish_raw)
        start = _parse_date(start_raw)

        pct_complete = getattr(task, "percent_complete", None)
        if pct_complete is None:
            pct_complete = 0.0
        try:
            pct_complete = float(pct_complete)
        except (TypeError, ValueError):
            pct_complete = 0.0

        # Planned cost — try several common attribute names
        planned_cost: float | None = None
        for attr in ("planned_cost", "budgeted_cost", "baseline_cost", "cost", "budget"):
            raw = getattr(task, attr, None)
            if raw is not None:
                try:
                    planned_cost = float(raw)
                    has_cost_data = True
                    break
                except (TypeError, ValueError):
                    continue

        # Actual cost
        actual_cost_val: float | None = None
        for attr in ("actual_cost", "acwp", "cost_actual"):
            raw = getattr(task, attr, None)
            if raw is not None:
                try:
                    actual_cost_val = float(raw)
                    break
                except (TypeError, ValueError):
                    continue

        if planned_cost is None:
            # No cost data — use duration-based unit weight of 1.0 per day
            if start and finish:
                duration_days = max(1, (finish - start).days)
                planned_cost = float(duration_days)
            else:
                planned_cost = 1.0

        tasks_analysed += 1
        bac += planned_cost

        # BCWP — earned value: planned cost × percent complete
        task_bcwp = planned_cost * (pct_complete / 100.0)
        bcwp += task_bcwp

        # BCWS — planned value: planned cost for tasks that should be done by status_date
        if finish and finish <= status_date:
            bcws += planned_cost
        elif start and finish and start <= status_date < finish:
            # Partially elapsed — pro-rate
            total_days = max(1, (finish - start).days)
            elapsed_days = (status_date - start).days
            bcws += planned_cost * (elapsed_days / total_days)
        # else: not yet started — BCWS contribution is 0

        # ACWP
        if actual_cost_val is not None:
            acwp_total += actual_cost_val
        else:
            # Estimate from BCWP with a 10 % overrun assumption
            acwp_total += task_bcwp * 1.1

    if not has_cost_data:
        warnings.append(
            "No cost fields found on tasks; schedule-based unit weights used. "
            "Monetary values are in arbitrary units, not currency."
        )
        currency_symbol = ""

    # Guard against division by zero
    acwp = acwp_total
    spi = round(bcwp / bcws, 4) if bcws > 0 else 0.0
    cpi = round(bcwp / acwp, 4) if acwp > 0 else 0.0
    sv = round(bcwp - bcws, 2)
    cv = round(bcwp - acwp, 2)
    eac = round(bac / cpi, 2) if cpi > 0 else 0.0
    etc = round(eac - acwp, 2)
    vac = round(bac - eac, 2)
    remaining_work = bac - bcwp
    remaining_budget = bac - acwp
    tcpi = round(remaining_work / remaining_budget, 4) if remaining_budget > 0 else 0.0

    return {
        "bcws": round(bcws, 2),
        "bcwp": round(bcwp, 2),
        "acwp": round(acwp, 2),
        "bac": round(bac, 2),
        "spi": spi,
        "cpi": cpi,
        "sv": sv,
        "cv": cv,
        "eac": eac,
        "etc_": etc,
        "vac": vac,
        "tcpi": tcpi,
        "has_cost_data": has_cost_data,
        "currency": currency_symbol,
        "warnings": warnings,
        "tasks_analysed": tasks_analysed,
    }


# ---------------------------------------------------------------------------
# S-curve data
# ---------------------------------------------------------------------------


def _build_scurve_data(
    project: Any,
    status_date: date,
    num_points: int = 20,
) -> tuple[list[str], list[float], list[float]]:
    """
    Return (labels, planned_values, earned_values) for the S-curve chart.
    Samples the cumulative planned and earned value across the project timeline.
    """
    tasks = getattr(project, "tasks", None) or []
    task_data: list[dict[str, Any]] = []

    for task in tasks:
        finish_raw = getattr(task, "finish_date", None) or getattr(task, "baseline_finish", None)
        start_raw = getattr(task, "start_date", None)
        finish = _parse_date(finish_raw)
        start = _parse_date(start_raw)
        if not start or not finish:
            continue

        pct_complete = getattr(task, "percent_complete", None) or 0.0
        try:
            pct_complete = float(pct_complete)
        except (TypeError, ValueError):
            pct_complete = 0.0

        planned_cost: float = 1.0
        for attr in ("planned_cost", "budgeted_cost", "baseline_cost", "cost", "budget"):
            raw = getattr(task, attr, None)
            if raw is not None:
                try:
                    planned_cost = float(raw)
                    break
                except (TypeError, ValueError):
                    continue

        task_data.append({
            "start": start,
            "finish": finish,
            "planned_cost": planned_cost,
            "bcwp": planned_cost * (pct_complete / 100.0),
        })

    if not task_data:
        return [], [], []

    min_date = min(t["start"] for t in task_data)
    max_date = max(t["finish"] for t in task_data)
    total_days = max(1, (max_date - min_date).days)
    step = max(1, total_days // num_points)

    labels: list[str] = []
    planned_values: list[float] = []
    earned_values: list[float] = []

    sample = min_date
    while sample <= max_date + timedelta(days=step):
        cum_planned = 0.0
        cum_earned = 0.0
        for t in task_data:
            if t["finish"] <= sample:
                cum_planned += t["planned_cost"]
                # Earned: only count if this sample point is at or before the status_date
                if sample <= status_date:
                    cum_earned += t["bcwp"]
            elif t["start"] <= sample < t["finish"]:
                total = max(1, (t["finish"] - t["start"]).days)
                elapsed = (sample - t["start"]).days
                pro_rated = t["planned_cost"] * (elapsed / total)
                cum_planned += pro_rated
                if sample <= status_date:
                    # Earned pro-rated by percent complete up to status date
                    cum_earned += t["bcwp"] * (elapsed / total)
        labels.append(sample.strftime("%b %y"))
        planned_values.append(round(cum_planned, 2))
        earned_values.append(round(cum_earned, 2))
        sample += timedelta(days=step)

    return labels, planned_values, earned_values


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------


def _build_html(
    project_name: str,
    status_date: date,
    metrics: dict[str, Any],
    scurve_labels: list[str],
    scurve_planned: list[float],
    scurve_earned: list[float],
) -> str:
    """Render a fully self-contained HTML dashboard for the EV report."""
    sym = metrics["currency"]
    bcws = metrics["bcws"]
    bcwp = metrics["bcwp"]
    acwp = metrics["acwp"]
    bac = metrics["bac"]
    eac = metrics["eac"]
    etc_ = metrics["etc_"]
    vac = metrics["vac"]
    spi = metrics["spi"]
    cpi = metrics["cpi"]
    sv = metrics["sv"]
    cv = metrics["cv"]
    tcpi = metrics["tcpi"]
    warnings = metrics["warnings"]
    tasks_analysed = metrics["tasks_analysed"]

    status_label, status_colour = _overall_status(spi, cpi)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Bullet-point interpretations
    bullets: list[str] = []
    bullets.append(
        f"Schedule Performance Index (SPI) is {spi:.2f} — {_interpret_spi(spi)}. "
        f"The project has earned {sym}{bcwp:,.0f} of planned work against a schedule "
        f"target of {sym}{bcws:,.0f}."
    )
    bullets.append(
        f"Cost Performance Index (CPI) is {cpi:.2f} — {_interpret_cpi(cpi)}. "
        f"Actual spend to date is {sym}{acwp:,.0f} against earned value of "
        f"{sym}{bcwp:,.0f}."
    )
    if eac > 0:
        bullets.append(
            f"Estimate at Completion (EAC) is {sym}{eac:,.0f} against a Budget at "
            f"Completion (BAC) of {sym}{bac:,.0f}, giving a Variance at Completion "
            f"(VAC) of {sym}{vac:,.0f}."
        )
    if tcpi > 0:
        tcpi_msg = (
            "achievable if current performance is maintained"
            if tcpi <= 1.1
            else "challenging — performance must improve significantly to deliver within budget"
        )
        bullets.append(
            f"To-Complete Performance Index (TCPI) is {tcpi:.2f}, which is {tcpi_msg}."
        )

    bullets_html = "".join(f'<li style="margin-bottom:6px">{b}</li>' for b in bullets)
    warnings_html = (
        "".join(
            f'<p style="margin:4px 0;color:#d97706;font-size:12px">Warning: {w}</p>'
            for w in warnings
        )
        if warnings
        else ""
    )

    # ---- S-curve SVG -------------------------------------------------------
    svg_html = _build_scurve_svg(scurve_labels, scurve_planned, scurve_earned)

    # ---- Performance indices rows ------------------------------------------
    def index_row(name: str, value: float, description: str) -> str:
        colour = _spi_colour(value)
        if value >= 0.95:
            badge_bg = "#dcfce7"
            badge_text = "#15803d"
        elif value >= 0.80:
            badge_bg = "#fef3c7"
            badge_text = "#92400e"
        else:
            badge_bg = "#fee2e2"
            badge_text = "#991b1b"
        return (
            f'<tr style="border-bottom:1px solid #e2e8f0">'
            f'<td style="padding:10px 14px;font-weight:600;color:#334155">{name}</td>'
            f'<td style="padding:10px 14px;text-align:center">'
            f'<span style="background:{badge_bg};color:{badge_text};padding:3px 10px;'
            f'border-radius:12px;font-weight:700;font-size:15px">{value:.3f}</span></td>'
            f'<td style="padding:10px 14px;color:#64748b;font-size:13px">{description}</td>'
            f'</tr>'
        )

    indices_rows = (
        index_row("SPI", spi, _interpret_spi(spi))
        + index_row("CPI", cpi, _interpret_cpi(cpi))
        + index_row("TCPI", tcpi, "To-Complete Performance Index (target cost efficiency required)")
    )

    # ---- Monetary metrics rows ---------------------------------------------
    def money_row(label: str, value: float, note: str = "") -> str:
        formatted = _fmt_currency(value, sym) if sym else f"{value:,.2f}"
        colour = "#334155"
        if value < 0:
            colour = "#dc2626"
        elif value > 0 and label.startswith(("SV", "CV", "VAC")):
            colour = "#16a34a"
        return (
            f'<tr style="border-bottom:1px solid #e2e8f0">'
            f'<td style="padding:10px 14px;color:#64748b;font-size:13px">{label}</td>'
            f'<td style="padding:10px 14px;font-weight:700;color:{colour};font-size:15px">'
            f'{formatted}</td>'
            f'<td style="padding:10px 14px;color:#94a3b8;font-size:12px">{note}</td>'
            f'</tr>'
        )

    money_rows = (
        money_row("BCWS — Budgeted Cost of Work Scheduled", bcws, "Planned value at status date")
        + money_row("BCWP — Budgeted Cost of Work Performed", bcwp, "Earned value")
        + money_row("ACWP — Actual Cost of Work Performed", acwp, "Actual spend to date")
        + money_row("BAC — Budget at Completion", bac, "Total planned budget")
        + money_row("EAC — Estimate at Completion", eac, "Forecast final cost")
        + money_row("ETC — Estimate to Complete", etc_, "Remaining cost forecast")
        + money_row("VAC — Variance at Completion", vac, "BAC minus EAC")
        + money_row("SV — Schedule Variance", sv, "BCWP minus BCWS")
        + money_row("CV — Cost Variance", cv, "BCWP minus ACWP")
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{project_name} — EV Dashboard</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      background: #f8fafc;
      color: #1e293b;
      min-height: 100vh;
    }}
    header {{
      background: #334155;
      padding: 12px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .logo-mark {{
      width: 32px; height: 32px;
      background: #D946EF;
      border-radius: 8px;
      display: flex; align-items: center; justify-content: center;
      font-weight: 700; color: #fff; font-size: 18px; flex-shrink: 0;
    }}
    .logo-text {{ margin-left: 10px; }}
    .logo-text h1 {{ color: #fff; font-size: 17px; font-weight: 700; line-height: 1.2; }}
    .logo-text p {{ color: #94a3b8; font-size: 11px; margin-top: 1px; }}
    .header-right {{ color: #94a3b8; font-size: 12px; }}
    main {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px; }}
    .project-header {{
      background: #0b1f4b;
      border-radius: 16px;
      padding: 24px;
      color: #fff;
      margin-bottom: 20px;
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
    }}
    .project-title {{ font-size: 22px; font-weight: 700; margin-bottom: 4px; }}
    .project-meta {{ color: #94a3b8; font-size: 13px; }}
    .status-badge {{
      padding: 6px 18px;
      border-radius: 20px;
      font-weight: 700;
      font-size: 14px;
      letter-spacing: 0.05em;
    }}
    .card {{
      background: #fff;
      border: 1px solid #e2e8f0;
      border-radius: 16px;
      padding: 20px;
      margin-bottom: 20px;
    }}
    .card h2 {{
      font-size: 14px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #64748b;
      margin-bottom: 16px;
    }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      margin-bottom: 20px;
    }}
    .kpi-card {{
      background: #fff;
      border: 1px solid #e2e8f0;
      border-radius: 16px;
      padding: 20px;
      text-align: center;
    }}
    .kpi-label {{
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      color: #64748b;
      margin-bottom: 8px;
    }}
    .kpi-value {{
      font-size: 26px;
      font-weight: 700;
    }}
    .kpi-sub {{
      font-size: 11px;
      color: #94a3b8;
      margin-top: 4px;
    }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{
      text-align: left;
      padding: 8px 14px;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #64748b;
      background: #f8fafc;
      border-bottom: 2px solid #e2e8f0;
    }}
    .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
    @media (max-width: 700px) {{ .two-col {{ grid-template-columns: 1fr; }} }}
    .bullets {{ list-style: disc; padding-left: 20px; color: #334155; font-size: 14px; line-height: 1.7; }}
    footer {{
      text-align: center;
      padding: 20px;
      color: #94a3b8;
      font-size: 12px;
      border-top: 1px solid #e2e8f0;
      margin-top: 20px;
    }}
    @media print {{
      body {{ background: #fff; }}
      header {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    }}
  </style>
</head>
<body>

  <header>
    <div style="display:flex;align-items:center">
      <div class="logo-mark">T</div>
      <div class="logo-text">
        <h1>TortoiseAI</h1>
        <p>PDA Platform &middot; Earned Value Analysis</p>
      </div>
    </div>
    <div class="header-right">Generated {generated_at}</div>
  </header>

  <main>

    <!-- Project header -->
    <div class="project-header">
      <div>
        <div class="project-title">{project_name}</div>
        <div class="project-meta">
          Status date: {status_date.isoformat()} &nbsp;&middot;&nbsp;
          Tasks analysed: {tasks_analysed}
        </div>
      </div>
      <div>
        <span class="status-badge"
              style="background:{status_colour}22;color:{status_colour};">
          {status_label}
        </span>
      </div>
    </div>

    {f'<div class="card" style="border-color:#fde68a;background:#fffbeb">{warnings_html}</div>' if warnings_html else ''}

    <!-- KPI cards -->
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">SPI</div>
        <div class="kpi-value" style="color:{_spi_colour(spi)}">{spi:.2f}</div>
        <div class="kpi-sub">{_interpret_spi(spi)}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">CPI</div>
        <div class="kpi-value" style="color:{_cpi_colour(cpi)}">{cpi:.2f}</div>
        <div class="kpi-sub">{_interpret_cpi(cpi)}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">BAC</div>
        <div class="kpi-value" style="color:#334155">{_fmt_currency(bac, sym) if sym else f'{bac:,.0f}'}</div>
        <div class="kpi-sub">Budget at Completion</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">EAC</div>
        <div class="kpi-value" style="color:{'#dc2626' if eac > bac else '#16a34a'}">{_fmt_currency(eac, sym) if sym else f'{eac:,.0f}'}</div>
        <div class="kpi-sub">Estimate at Completion</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">TCPI</div>
        <div class="kpi-value" style="color:{_spi_colour(1/tcpi if tcpi > 0 else 0)}">{tcpi:.2f}</div>
        <div class="kpi-sub">To-Complete Performance Index</div>
      </div>
    </div>

    <div class="two-col">

      <!-- EV metrics table -->
      <div class="card">
        <h2>EV Metrics</h2>
        <table>
          <thead><tr>
            <th>Metric</th><th>Value</th><th>Note</th>
          </tr></thead>
          <tbody>{money_rows}</tbody>
        </table>
      </div>

      <!-- Performance indices table -->
      <div class="card">
        <h2>Performance Indices</h2>
        <table>
          <thead><tr>
            <th>Index</th><th style="text-align:center">Value</th><th>Interpretation</th>
          </tr></thead>
          <tbody>{indices_rows}</tbody>
        </table>

        <div style="margin-top:16px;padding-top:12px;border-top:1px solid #e2e8f0">
          <p style="font-size:11px;color:#94a3b8;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px">Key</p>
          <p style="font-size:12px;color:#64748b">
            <span style="background:#dcfce7;color:#15803d;padding:1px 7px;border-radius:8px;font-size:11px;font-weight:600">Green</span>
            &ge; 0.95 &nbsp;
            <span style="background:#fef3c7;color:#92400e;padding:1px 7px;border-radius:8px;font-size:11px;font-weight:600">Amber</span>
            0.80 – 0.95 &nbsp;
            <span style="background:#fee2e2;color:#991b1b;padding:1px 7px;border-radius:8px;font-size:11px;font-weight:600">Red</span>
            &lt; 0.80
          </p>
        </div>
      </div>

    </div>

    <!-- S-curve -->
    <div class="card">
      <h2>S-Curve: Planned Value vs Earned Value</h2>
      {svg_html}
    </div>

    <!-- Summary -->
    <div class="card">
      <h2>Summary</h2>
      <ul class="bullets">
        {bullets_html}
      </ul>
    </div>

  </main>

  <footer>
    &copy; {datetime.now().year} TortoiseAI &middot; PDA Platform &middot; Earned Value Analysis &middot; {project_name}
  </footer>

</body>
</html>"""


# ---------------------------------------------------------------------------
# S-curve SVG builder
# ---------------------------------------------------------------------------


def _build_scurve_svg(
    labels: list[str],
    planned: list[float],
    earned: list[float],
    width: int = 800,
    height: int = 300,
) -> str:
    """Render a simple S-curve as an inline SVG with axes and legend."""
    if not labels or not planned:
        return '<p style="color:#94a3b8;font-size:13px">Insufficient date data on tasks to render S-curve.</p>'

    pad_left = 70
    pad_right = 20
    pad_top = 20
    pad_bottom = 50

    chart_w = width - pad_left - pad_right
    chart_h = height - pad_top - pad_bottom

    max_val = max(max(planned), max(earned) if earned else 0) or 1.0
    n = len(labels)

    def x_coord(i: int) -> float:
        return pad_left + (i / max(n - 1, 1)) * chart_w

    def y_coord(v: float) -> float:
        return pad_top + chart_h - (v / max_val) * chart_h

    # Planned value polyline
    planned_pts = " ".join(f"{x_coord(i):.1f},{y_coord(v):.1f}" for i, v in enumerate(planned))
    # Earned value polyline
    earned_pts = " ".join(f"{x_coord(i):.1f},{y_coord(v):.1f}" for i, v in enumerate(earned)) if earned else ""

    # X-axis tick labels — show at most 10
    step = max(1, n // 10)
    x_ticks = ""
    for i in range(0, n, step):
        xi = x_coord(i)
        x_ticks += (
            f'<text x="{xi:.1f}" y="{pad_top + chart_h + 18}" '
            f'text-anchor="middle" font-size="10" fill="#94a3b8">{labels[i]}</text>'
        )

    # Y-axis tick labels — 5 ticks
    y_ticks = ""
    for j in range(6):
        frac = j / 5
        val = max_val * frac
        yi = y_coord(val)
        label = _fmt_currency(val, "") if val >= 1000 else f"{val:,.0f}"
        y_ticks += (
            f'<line x1="{pad_left - 4}" y1="{yi:.1f}" x2="{pad_left}" y2="{yi:.1f}" '
            f'stroke="#e2e8f0" stroke-width="1"/>'
            f'<line x1="{pad_left}" y1="{yi:.1f}" x2="{pad_left + chart_w}" y2="{yi:.1f}" '
            f'stroke="#e2e8f0" stroke-width="1" stroke-dasharray="4,4"/>'
            f'<text x="{pad_left - 8}" y="{yi + 4:.1f}" text-anchor="end" '
            f'font-size="10" fill="#94a3b8">{label}</text>'
        )

    earned_line = (
        f'<polyline points="{earned_pts}" fill="none" stroke="#D946EF" '
        f'stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>'
        if earned_pts
        else ""
    )

    legend_y = pad_top + chart_h + 38
    legend = (
        f'<rect x="{pad_left}" y="{legend_y}" width="14" height="3" fill="#10B981" rx="2"/>'
        f'<text x="{pad_left + 18}" y="{legend_y + 4}" font-size="11" fill="#64748b">Planned Value (BCWS)</text>'
        f'<rect x="{pad_left + 160}" y="{legend_y}" width="14" height="3" fill="#D946EF" rx="2"/>'
        f'<text x="{pad_left + 178}" y="{legend_y + 4}" font-size="11" fill="#64748b">Earned Value (BCWP)</text>'
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height + 20}"
     style="width:100%;max-width:{width}px;height:auto;display:block">
  <!-- Grid and axes -->
  {y_ticks}
  <!-- Axis lines -->
  <line x1="{pad_left}" y1="{pad_top}" x2="{pad_left}" y2="{pad_top + chart_h}"
        stroke="#cbd5e1" stroke-width="1.5"/>
  <line x1="{pad_left}" y1="{pad_top + chart_h}" x2="{pad_left + chart_w}" y2="{pad_top + chart_h}"
        stroke="#cbd5e1" stroke-width="1.5"/>
  <!-- X-axis labels -->
  {x_ticks}
  <!-- Planned value line -->
  <polyline points="{planned_pts}" fill="none" stroke="#10B981"
            stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>
  <!-- Earned value line -->
  {earned_line}
  <!-- Legend -->
  {legend}
</svg>"""


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


async def _compute_ev_metrics(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for the compute_ev_metrics tool."""
    project_id: str | None = arguments.get("project_id")
    if not project_id:
        return [TextContent(type="text", text=json.dumps({
            "error": "project_id is required."
        }))]

    project = project_store.get(project_id)
    if project is None:
        return [TextContent(type="text", text=json.dumps({
            "error": (
                f"Project '{project_id}' not found. "
                "Please call load_project first to load the project data."
            )
        }))]

    status_date_str: str | None = arguments.get("status_date")
    if status_date_str:
        parsed = _parse_date(status_date_str)
        status_date = parsed if parsed else date.today()
    else:
        status_date = date.today()

    try:
        metrics = _compute_metrics(project, status_date)
    except Exception as exc:
        logger.exception("Error computing EV metrics: %s", exc)
        return [TextContent(type="text", text=json.dumps({
            "error": f"Failed to compute EV metrics: {exc}"
        }))]

    sym = metrics["currency"]

    output = {
        "project_id": project_id,
        "project_name": getattr(project, "name", project_id),
        "status_date": status_date.isoformat(),
        "tasks_analysed": metrics["tasks_analysed"],
        "has_cost_data": metrics["has_cost_data"],
        "currency": sym or "units",
        "metrics": {
            "BCWS": metrics["bcws"],
            "BCWP": metrics["bcwp"],
            "ACWP": metrics["acwp"],
            "BAC": metrics["bac"],
            "SV": metrics["sv"],
            "CV": metrics["cv"],
            "SPI": metrics["spi"],
            "CPI": metrics["cpi"],
            "EAC": metrics["eac"],
            "ETC": metrics["etc_"],
            "VAC": metrics["vac"],
            "TCPI": metrics["tcpi"],
        },
        "interpretations": {
            "SPI": _interpret_spi(metrics["spi"]),
            "CPI": _interpret_cpi(metrics["cpi"]),
            "overall_status": _overall_status(metrics["spi"], metrics["cpi"])[0],
        },
        "warnings": metrics["warnings"],
    }
    return [TextContent(type="text", text=json.dumps(output, indent=2))]


async def _generate_ev_dashboard(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for the generate_ev_dashboard tool."""
    project_id: str | None = arguments.get("project_id")
    if not project_id:
        return [TextContent(type="text", text=json.dumps({
            "error": "project_id is required."
        }))]

    project = project_store.get(project_id)
    if project is None:
        return [TextContent(type="text", text=json.dumps({
            "error": (
                f"Project '{project_id}' not found. "
                "Please call load_project first to load the project data."
            )
        }))]

    status_date_str: str | None = arguments.get("status_date")
    if status_date_str:
        parsed = _parse_date(status_date_str)
        status_date = parsed if parsed else date.today()
    else:
        status_date = date.today()

    output_path: str | None = arguments.get("output_path")
    project_name = getattr(project, "name", project_id) or project_id

    try:
        metrics = _compute_metrics(project, status_date)
        scurve_labels, scurve_planned, scurve_earned = _build_scurve_data(
            project, status_date
        )
        html = _build_html(
            project_name=project_name,
            status_date=status_date,
            metrics=metrics,
            scurve_labels=scurve_labels,
            scurve_planned=scurve_planned,
            scurve_earned=scurve_earned,
        )
    except Exception as exc:
        logger.exception("Error generating EV dashboard: %s", exc)
        return [TextContent(type="text", text=json.dumps({
            "error": f"Failed to generate EV dashboard: {exc}"
        }))]

    if output_path:
        try:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(html, encoding="utf-8")
            return [TextContent(type="text", text=json.dumps({
                "message": f"EV dashboard written to {out}. Open in any browser — works offline.",
                "file_path": str(out),
                "project_id": project_id,
            }, indent=2))]
        except OSError as exc:
            return [TextContent(type="text", text=json.dumps({
                "error": f"Failed to write dashboard to '{output_path}': {exc}"
            }))]

    # Return HTML as text
    return [TextContent(type="text", text=html)]

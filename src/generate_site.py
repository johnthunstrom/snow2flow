"""
Generate static HTML pages for the snow-to-flow site.
One page per river, plus an index page.
"""

import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Year color scheme
#
# Last digit of water year → color family (10 families, one per digit 0–9)
# Decade of water year     → shade within that family (lighter=older, vivid=recent)
#
# Decade indices: 0=1980s, 1=1990s, 2=2000s, 3=2010s, 4=2020s
#
# Reading the table:  DIGIT_PALETTES[last_digit][decade_index]
# So 2026 → digit 6 (blue), decade 4 (2020s) → darkest/most vivid blue
#    2016 → digit 6 (blue), decade 3 (2010s) → slightly lighter blue
#    1996 → digit 6 (blue), decade 1 (1990s) → pale blue
# ---------------------------------------------------------------------------
DIGIT_PALETTES = {
    0: ["#c8b0e0", "#a878cc", "#8840b0", "#681890", "#500878"],  # violet
    1: ["#f0a8a8", "#e06868", "#c82828", "#a00808", "#780000"],  # red
    2: ["#f8cc98", "#f0a048", "#d87020", "#b04800", "#883000"],  # orange
    3: ["#ece870", "#d8c830", "#b8a000", "#907800", "#685400"],  # gold/amber
    4: ["#c0e890", "#90d048", "#60a810", "#3c7808", "#1a5002"],  # lime/yellow-green
    5: ["#90d890", "#50b850", "#188818", "#0a6010", "#065008"],  # green
    6: ["#90c8f8", "#4898e0", "#1060c8", "#0840a8", "#0428a0"],  # blue
    7: ["#b8a8e0", "#8878c8", "#5848a8", "#302888", "#100870"],  # indigo
    8: ["#f8a0c8", "#e85898", "#c81860", "#980040", "#680030"],  # magenta/pink
    9: ["#88dce0", "#38b8c0", "#0888a0", "#065878", "#044058"],  # teal/cyan
}

# Line widths by decade (thinner=older, thicker=more recent)
DECADE_WIDTHS = [0.8, 1.0, 1.2, 1.6, 2.2]  # indices 0–4

# Current year gets extra weight so it always reads as "now"
CURRENT_YEAR_WIDTH = 3.0


def _current_water_year() -> int:
    today = date.today()
    return today.year + 1 if today.month >= 10 else today.year


def _decade_index(wy: int) -> int:
    """Return 0–4 for the decade: 0=1980s … 4=2020s+"""
    return min(4, max(0, (wy - 1980) // 10))


def _year_color(wy: int, current_wy: int) -> str:
    if wy == current_wy:
        # Current year: use the most vivid shade of its digit family
        return DIGIT_PALETTES[wy % 10][4]
    return DIGIT_PALETTES[wy % 10][_decade_index(wy)]


def _year_width(wy: int, current_wy: int) -> float:
    if wy == current_wy:
        return CURRENT_YEAR_WIDTH
    return DECADE_WIDTHS[_decade_index(wy)]


def make_chart(site_config: dict, flow_wy: pd.DataFrame,
               swe_wy: pd.DataFrame,
               temp_wy: pd.DataFrame) -> tuple[str, int, list[int]]:
    """
    Build a Plotly figure with:
      Row 1 (tall): SWE (left axis, dotted) + streamflow (right axis, solid)
      Row 2 (short): basin-average daily temperature (°F)

    Returns (html_div, current_water_year, default_visible_years).
    """
    has_temp = not temp_wy.empty

    if has_temp:
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            row_heights=[5, 1],
            specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
            vertical_spacing=0.03,
        )
        chart_height = 720
    else:
        fig = make_subplots(rows=1, cols=1, specs=[[{"secondary_y": True}]])
        chart_height = 580

    all_years = sorted(set(flow_wy.columns) | set(swe_wy.columns) | set(temp_wy.columns))
    current_wy = _current_water_year()

    # Last 5 years visible on load
    visible_years = set(all_years[-5:])

    # --- SWE traces (row 1, left axis, dotted) ---
    for wy in all_years:
        if wy not in swe_wy.columns:
            continue
        s = swe_wy[wy].dropna()
        color = _year_color(wy, current_wy)
        width = _year_width(wy, current_wy)
        fig.add_trace(
            go.Scatter(
                x=s.index,
                y=s.values,
                name=str(wy),
                legendgroup=str(wy),
                showlegend=True,
                visible=True if wy in visible_years else "legendonly",
                line=dict(color=color, width=width, dash="dot"),
                hovertemplate=f"<b>{wy} SWE</b><br>%{{x|%b %d}}: %{{y:.1f}} in<extra></extra>",
            ),
            secondary_y=False, row=1, col=1,
        )

    # --- Streamflow traces (row 1, right axis, solid) ---
    for wy in all_years:
        if wy not in flow_wy.columns:
            continue
        s = flow_wy[wy].dropna()
        color = _year_color(wy, current_wy)
        width = _year_width(wy, current_wy)
        fig.add_trace(
            go.Scatter(
                x=s.index,
                y=s.values,
                name=str(wy),
                legendgroup=str(wy),
                showlegend=False,
                visible=True if wy in visible_years else "legendonly",
                line=dict(color=color, width=width),
                hovertemplate=f"<b>{wy} Flow</b><br>%{{x|%b %d}}: %{{y:,.0f}} cfs<extra></extra>",
            ),
            secondary_y=True, row=1, col=1,
        )

    # --- Temperature traces (row 2) ---
    if has_temp:
        for wy in all_years:
            if wy not in temp_wy.columns:
                continue
            s = temp_wy[wy].dropna()
            color = _year_color(wy, current_wy)
            width = _year_width(wy, current_wy)
            fig.add_trace(
                go.Scatter(
                    x=s.index,
                    y=s.values,
                    name=str(wy),
                    legendgroup=str(wy),
                    showlegend=False,
                    visible=True if wy in visible_years else "legendonly",
                    line=dict(color=color, width=max(0.6, width * 0.7)),
                    hovertemplate=f"<b>{wy} Temp</b><br>%{{x|%b %d}}: %{{y:.1f}}°F<extra></extra>",
                ),
                row=2, col=1,
            )
        # 32°F freezing reference line
        fig.add_hline(
            y=32, line_dash="dot", line_color="#6699cc", line_width=1,
            row=2, col=1,
        )

    # --- Axes ---
    fig.update_xaxes(
        tickformat="%b",
        dtick="M1",
        ticklabelmode="period",
        title_text="",
        showgrid=True,
        gridcolor="#e0e0e0",
    )
    fig.update_yaxes(
        title_text="SWE (in)",
        secondary_y=False, row=1, col=1,
        rangemode="tozero",
        showgrid=True,
        gridcolor="#e0e0e0",
    )
    fig.update_yaxes(
        title_text="Flow (cfs)",
        secondary_y=True, row=1, col=1,
        rangemode="tozero",
        showgrid=False,
    )
    if has_temp:
        fig.update_yaxes(
            title_text="Temp (°F)",
            row=2, col=1,
            showgrid=True,
            gridcolor="#e0e0e0",
            tickfont=dict(size=9),
            title_font=dict(size=10),
            zeroline=False,
        )

    fig.update_layout(
        title=dict(
            text=f"{site_config['name']}<br><sup>{site_config['subtitle']}</sup>",
            font=dict(size=18),
        ),
        hovermode="x unified",
        legend=dict(
            orientation="v",
            x=1.02,
            y=1,
            xanchor="left",
            yanchor="top",
            title=dict(text="Year<br><sup>··· SWE · — flow</sup>"),
            font=dict(size=10),
            tracegroupgap=1,
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="#e0e0e0",
            borderwidth=1,
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=chart_height,
        margin=dict(l=60, r=120, t=80, b=60),
    )

    chart_html = fig.to_html(full_html=False, include_plotlyjs=False, div_id="chart")
    return chart_html, current_wy, sorted(visible_years)


def _swe_comparison_data(swe_wy: pd.DataFrame, current_wy: int) -> dict:
    """
    Pre-compute SWE comparison data for the 'Show 5 Most Similar Years' button.
    Finds the last date with current-year SWE data, then collects every other
    year's SWE at that same proxy date.

    Returns a dict suitable for JSON-serialization into the page's JavaScript.
    """
    if swe_wy.empty or current_wy not in swe_wy.columns:
        return {}

    cur = swe_wy[current_wy].dropna()
    if cur.empty:
        return {}

    ref_date = cur.index[-1]          # proxy date (2000-2001 range)
    ref_swe = float(cur.iloc[-1])

    historical = {}
    for wy in swe_wy.columns:
        if wy == current_wy:
            continue
        if ref_date in swe_wy.index:
            val = swe_wy.loc[ref_date, wy]
            if pd.notna(val):
                historical[str(wy)] = round(float(val), 1)

    return {
        "ref_date": ref_date.strftime("%B %-d"),   # e.g. "March 7"
        "ref_swe": round(ref_swe, 1),
        "historical": historical,
    }


def render_page(site_config: dict, flow_wy: pd.DataFrame, swe_wy: pd.DataFrame,
                temp_wy: pd.DataFrame, output_path: Path) -> None:
    """Render a single river page as a self-contained HTML file."""
    chart_div, current_wy, default_visible = make_chart(site_config, flow_wy, swe_wy, temp_wy)

    snotel_list = "\n".join(
        f'          <li>{s["name"]} (SNOTEL {s["id"]})</li>'
        for s in site_config["snotel_sites"]
    )

    gauge = site_config["gauge"]
    updated = date.today().strftime("%B %d, %Y")

    # JSON-encode for safe injection into the page's JavaScript
    current_wy_js = json.dumps(current_wy)
    default_visible_js = json.dumps([str(y) for y in default_visible])
    swe_comparison_js = json.dumps(_swe_comparison_data(swe_wy, current_wy))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
  <meta http-equiv="Pragma" content="no-cache">
  <meta http-equiv="Expires" content="0">
  <title>{site_config['name']} – Snow to Flow</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f5f5f5;
      color: #333;
    }}
    header {{
      background: #1a3a5c;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 2rem 0 0;
      overflow: hidden;
    }}
    header a.logo {{ line-height: 0; }}
    header a.logo img {{ height: 72px; display: block; }}
    header a.back {{
      color: #cce0f5;
      text-decoration: none;
      font-size: 0.9rem;
      white-space: nowrap;
    }}
    header a.back:hover {{ text-decoration: underline; }}
    .container {{ max-width: 1200px; margin: 0 auto; padding: 1.5rem; }}
    .chart-controls {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin-bottom: 0.75rem;
      flex-wrap: wrap;
    }}
    .btn {{
      padding: 0.4rem 0.9rem;
      border: none;
      border-radius: 5px;
      cursor: pointer;
      font-size: 0.85rem;
      font-family: inherit;
      transition: opacity 0.15s, transform 0.1s;
    }}
    .btn:hover {{ opacity: 0.85; transform: translateY(-1px); }}
    .btn-similar {{
      background: #2c5f8a;
      color: white;
    }}
    .btn-reset {{
      background: #e0e8f0;
      color: #2c5f8a;
    }}
    .similar-label {{
      font-size: 0.82rem;
      color: #555;
      font-style: italic;
    }}
    .chart-wrapper {{
      background: white;
      border-radius: 8px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.1);
      padding: 1rem;
      margin-bottom: 1.5rem;
    }}
    .meta {{
      background: white;
      border-radius: 8px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.1);
      padding: 1.25rem 1.5rem;
      font-size: 0.9rem;
      line-height: 1.6;
    }}
    .meta h3 {{ margin-bottom: 0.5rem; font-size: 1rem; color: #2c5f8a; }}
    .meta ul {{ padding-left: 1.25rem; }}
    .meta .cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
    footer {{
      text-align: center;
      padding: 1rem;
      font-size: 0.8rem;
      color: #888;
    }}
    @media (max-width: 600px) {{ .meta .cols {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <a class="logo" href="index.html">
      <img src="logo.png" alt="Snow to Flow">
    </a>
    <a class="back" href="index.html">← All Rivers</a>
  </header>

  <div class="container">
    <div class="chart-controls">
      <button class="btn btn-similar" onclick="showSimilarYears()">
        Show 5 Most Similar Years
      </button>
      <button class="btn btn-reset" onclick="resetToRecent()">
        Reset to Last 5 Years
      </button>
      <span class="similar-label" id="similar-label"></span>
    </div>

    <div class="chart-wrapper">
      {chart_div}
    </div>

    <div class="meta">
      <div class="cols">
        <div>
          <h3>Stream Gauge</h3>
          <p>{gauge['name']}<br>
          USGS Site {gauge['site_id']}<br>
          Right axis: daily mean discharge (cfs)</p>
        </div>
        <div>
          <h3>SNOTEL Sites (basin average SWE)</h3>
          <ul>
{snotel_list}
          </ul>
          <p style="margin-top:0.5rem">Left axis: mean snow water equivalent (inches)</p>
        </div>
      </div>
      <p style="margin-top:1rem; color:#666; font-size:0.85rem">
        The last 5 water years are shown on load — click any year in the legend to toggle it,
        or use <em>Show 5 Most Similar Years</em> to find historical years with the closest
        snowpack to today. Each year is color-coded by last digit (e.g. all &ldquo;6&rdquo;
        years are blue) with darker shades for more recent decades. The {current_wy - 1}&ndash;{current_wy}
        water year is the boldest line. Dotted&nbsp;=&nbsp;SWE, solid&nbsp;=&nbsp;streamflow.
        Updated: {updated}.
      </p>
    </div>
  </div>

  <footer>
    Data: <a href="https://waterservices.usgs.gov">USGS NWIS</a> &amp;
    <a href="https://www.nrcs.usda.gov/wps/portal/wcc/home">NRCS SNOTEL</a>.
    Inspired by the <a href="https://www.usbr.gov/uc/water/hydrodata/stf/">USBR Snow to Flow</a> tool.
  </footer>

  <script>
    var CURRENT_WY = {current_wy_js};
    var DEFAULT_VISIBLE = {default_visible_js};
    // Pre-computed SWE comparison: ref_date, ref_swe, historical {{year: swe}}
    var SWE_COMPARISON = {swe_comparison_js};

    function getChartDiv() {{
      return document.getElementById('chart') ||
             document.querySelector('.plotly-graph-div');
    }}

    function applyVisibility(showSet) {{
      var gd = getChartDiv();
      if (!gd || !gd.data) return;
      var showIdx = [], hideIdx = [];
      gd.data.forEach(function(t, i) {{
        if (showSet[t.legendgroup]) showIdx.push(i);
        else hideIdx.push(i);
      }});
      if (hideIdx.length) Plotly.restyle(gd, {{ visible: 'legendonly' }}, hideIdx);
      if (showIdx.length) Plotly.restyle(gd, {{ visible: true }}, showIdx);
    }}

    function showSimilarYears() {{
      if (!SWE_COMPARISON || !SWE_COMPARISON.historical) return;
      var hist = SWE_COMPARISON.historical;
      var refSwe = SWE_COMPARISON.ref_swe;
      var diffs = Object.keys(hist).map(function(yr) {{
        return {{ year: yr, diff: Math.abs(hist[yr] - refSwe) }};
      }});
      diffs.sort(function(a, b) {{ return a.diff - b.diff; }});
      var showSet = {{}};
      showSet[String(CURRENT_WY)] = true;
      diffs.slice(0, 5).forEach(function(d) {{ showSet[d.year] = true; }});
      applyVisibility(showSet);
      var years = diffs.slice(0, 5).map(function(d) {{ return d.year; }}).join(', ');
      document.getElementById('similar-label').textContent =
        'Nearest to ' + refSwe.toFixed(1) + '\u2033 SWE on ' + SWE_COMPARISON.ref_date +
        ' \u2014 ' + years;
    }}

    function resetToRecent() {{
      var showSet = {{}};
      DEFAULT_VISIBLE.forEach(function(y) {{ showSet[y] = true; }});
      applyVisibility(showSet);
      document.getElementById('similar-label').textContent = '';
    }}
  </script>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")
    log.info("Wrote %s", output_path)


def render_index(sites: list, output_dir: Path) -> None:
    """Render the index page listing all available rivers."""
    cards = ""
    for site in sites:
        page_file = f"{site['id']}.html"
        cards += f"""
    <a class="card" href="{page_file}">
      <h2>{site['name']}</h2>
      <p>{site['subtitle']}</p>
      <p class="gauge">USGS {site['gauge']['site_id']}</p>
    </a>"""

    updated = date.today().strftime("%B %d, %Y")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
  <meta http-equiv="Pragma" content="no-cache">
  <meta http-equiv="Expires" content="0">
  <title>Snow to Flow – Idaho Rivers</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f5f5f5;
      color: #333;
    }}
    header {{
      background: #1a3a5c;
      overflow: hidden;
      line-height: 0;
    }}
    header img {{ height: 90px; display: block; }}
    .container {{ max-width: 900px; margin: 2rem auto; padding: 0 1.5rem; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 1rem;
    }}
    .card {{
      display: block;
      background: white;
      border-radius: 8px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.1);
      padding: 1.25rem 1.5rem;
      text-decoration: none;
      color: #333;
      transition: box-shadow 0.15s, transform 0.15s;
    }}
    .card:hover {{
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
      transform: translateY(-2px);
    }}
    .card h2 {{ font-size: 1.1rem; color: #2c5f8a; margin-bottom: 0.25rem; }}
    .card p {{ font-size: 0.9rem; color: #666; }}
    .card .gauge {{ font-size: 0.8rem; color: #999; margin-top: 0.5rem; }}
    footer {{
      text-align: center;
      padding: 2rem 1rem;
      font-size: 0.8rem;
      color: #888;
    }}
  </style>
</head>
<body>
  <header>
    <img src="logo.png" alt="Snow to Flow — Idaho Rivers">
  </header>

  <div class="container">
    <p style="margin-bottom:1rem; color:#666; font-size:0.9rem">
      Daily snowpack (SWE) vs. streamflow, all water years. Updated: {updated}
    </p>
    <div class="grid">
{cards}
    </div>
  </div>

  <footer>
    Data: <a href="https://waterservices.usgs.gov">USGS NWIS</a> &amp;
    <a href="https://www.nrcs.usda.gov/wps/portal/wcc/home">NRCS SNOTEL</a>.
    Inspired by the <a href="https://www.usbr.gov/uc/water/hydrodata/stf/">USBR Snow to Flow</a> tool.
  </footer>
</body>
</html>
"""
    (output_dir / "index.html").write_text(html, encoding="utf-8")
    log.info("Wrote index.html")

"""
Generate static HTML pages for the snow-to-flow site.
One page per river, plus an index page.
"""

import json
import logging
import os
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

log = logging.getLogger(__name__)

# Water years to show highlighted (most recent N years stand out)
HIGHLIGHT_YEARS = 3

# Color palette for highlighted recent years
RECENT_COLORS = ["#e41a1c", "#ff7f00", "#4daf4a"]

# Color for historical years
HISTORICAL_COLOR = "rgba(150,150,150,0.4)"
CURRENT_COLOR = "#1f77b4"


def make_chart(site_config: dict, flow_wy: pd.DataFrame, swe_wy: pd.DataFrame) -> str:
    """
    Build a Plotly figure with SWE (left axis) and streamflow (right axis),
    one trace per water year. Returns the HTML div string.
    """
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    all_years = sorted(set(flow_wy.columns) | set(swe_wy.columns))
    current_wy = _current_water_year()

    # Split into historical and recent
    recent_years = [y for y in sorted(all_years) if y >= current_wy - HIGHLIGHT_YEARS and y < current_wy]
    historical_years = [y for y in all_years if y not in recent_years and y != current_wy]

    def year_color(wy):
        if wy == current_wy:
            return CURRENT_COLOR
        try:
            idx = recent_years.index(wy)
            return RECENT_COLORS[idx % len(RECENT_COLORS)]
        except ValueError:
            return HISTORICAL_COLOR

    def year_width(wy):
        return 2.5 if wy >= current_wy - HIGHLIGHT_YEARS else 1

    def year_visible(wy):
        # Historical years hidden by default (click legend to show)
        return True if wy >= current_wy - HIGHLIGHT_YEARS else "legendonly"

    # Add SWE traces (secondary y = False → left axis)
    for wy in all_years:
        if wy not in swe_wy.columns:
            continue
        s = swe_wy[wy].dropna()
        fig.add_trace(
            go.Scatter(
                x=s.index,
                y=s.values,
                name=f"{wy} SWE",
                legendgroup=str(wy),
                showlegend=True,
                visible=year_visible(wy),
                line=dict(color=year_color(wy), width=year_width(wy), dash="dot"),
                hovertemplate=f"<b>{wy} SWE</b><br>%{{x|%b %d}}: %{{y:.1f}} in<extra></extra>",
            ),
            secondary_y=False,
        )

    # Add streamflow traces (secondary y = True → right axis)
    for wy in all_years:
        if wy not in flow_wy.columns:
            continue
        s = flow_wy[wy].dropna()
        fig.add_trace(
            go.Scatter(
                x=s.index,
                y=s.values,
                name=f"{wy} Flow",
                legendgroup=str(wy),
                showlegend=False,  # Legend shared with SWE trace
                visible=year_visible(wy),
                line=dict(color=year_color(wy), width=year_width(wy)),
                hovertemplate=f"<b>{wy} Flow</b><br>%{{x|%b %d}}: %{{y:,.0f}} cfs<extra></extra>",
            ),
            secondary_y=True,
        )

    # X-axis: show month names only (water year Oct–Sep)
    fig.update_xaxes(
        tickformat="%b",
        dtick="M1",
        ticklabelmode="period",
        title_text="",
        showgrid=True,
        gridcolor="#e0e0e0",
    )

    fig.update_yaxes(
        title_text="Snow Water Equivalent (inches)",
        secondary_y=False,
        rangemode="tozero",
        showgrid=True,
        gridcolor="#e0e0e0",
    )
    fig.update_yaxes(
        title_text="Streamflow (cfs)",
        secondary_y=True,
        rangemode="tozero",
        showgrid=False,
    )

    fig.update_layout(
        title=dict(
            text=f"{site_config['name']}<br><sup>{site_config['subtitle']}</sup>",
            font=dict(size=18),
        ),
        hovermode="x unified",
        legend=dict(
            orientation="v",
            x=1.08,
            y=1,
            title="Water Year<br>(dotted=SWE, solid=Flow)",
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=550,
        margin=dict(l=60, r=180, t=80, b=60),
    )

    return fig.to_html(full_html=False, include_plotlyjs=False, div_id="chart")


def _current_water_year() -> int:
    today = date.today()
    return today.year + 1 if today.month >= 10 else today.year


def render_page(site_config: dict, flow_wy: pd.DataFrame, swe_wy: pd.DataFrame,
                output_path: Path) -> None:
    """Render a single river page as a self-contained HTML file."""
    chart_div = make_chart(site_config, flow_wy, swe_wy)

    snotel_list = "\n".join(
        f'          <li>{s["name"]} (SNOTEL {s["id"]})</li>'
        for s in site_config["snotel_sites"]
    )

    gauge = site_config["gauge"]
    updated = date.today().strftime("%B %d, %Y")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
      background: #2c5f8a;
      color: white;
      padding: 1rem 2rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    header a {{ color: #cce0f5; text-decoration: none; font-size: 0.9rem; }}
    header a:hover {{ text-decoration: underline; }}
    .container {{ max-width: 1200px; margin: 0 auto; padding: 1.5rem; }}
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
    <div>
      <strong>Snow to Flow</strong> — Idaho River Snowpack &amp; Streamflow
    </div>
    <a href="index.html">← All Rivers</a>
  </header>

  <div class="container">
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
        Historical years are shown in grey (click legend to toggle).
        The {_current_water_year() - 1}–{_current_water_year()} water year is highlighted in blue.
        Data updated: {updated}.
      </p>
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
  <title>Snow to Flow – Idaho Rivers</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f5f5f5;
      color: #333;
    }}
    header {{
      background: #2c5f8a;
      color: white;
      padding: 1.5rem 2rem;
    }}
    header h1 {{ font-size: 1.5rem; }}
    header p {{ font-size: 0.9rem; color: #cce0f5; margin-top: 0.25rem; }}
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
    <h1>Snow to Flow — Idaho Rivers</h1>
    <p>Daily snowpack (SWE) vs. streamflow, all water years. Updated: {updated}</p>
  </header>

  <div class="container">
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

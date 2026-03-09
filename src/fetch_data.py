"""
Data fetching for snow-to-flow:
  - USGS NWIS for daily streamflow
  - NRCS AWDB for SNOTEL snow water equivalent (SWE)
"""

import requests
import pandas as pd
from datetime import date, timedelta
import logging

log = logging.getLogger(__name__)

USGS_URL = "https://waterservices.usgs.gov/nwis/dv/"
NRCS_URL = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data"


def fetch_usgs_streamflow(site_id: str, start: str, end: str) -> pd.Series:
    """
    Fetch daily mean discharge (cfs) from USGS NWIS.

    Returns a pandas Series indexed by date, values in cfs.
    """
    params = {
        "format": "json",
        "sites": site_id,
        "parameterCd": "00060",
        "startDT": start,
        "endDT": end,
        "statCd": "00003",  # daily mean
    }
    resp = requests.get(USGS_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    ts = data["value"]["timeSeries"]
    if not ts:
        log.warning("No streamflow data for site %s", site_id)
        return pd.Series(dtype=float, name="flow_cfs")

    values = ts[0]["values"][0]["value"]
    records = {
        v["dateTime"][:10]: float(v["value"])
        for v in values
        if v["value"] not in (None, "-999999", "")
    }
    series = pd.Series(records, dtype=float, name="flow_cfs")
    series.index = pd.to_datetime(series.index)
    series.sort_index(inplace=True)
    return series


def fetch_nrcs_swe(site_id: str, state: str, start: str, end: str) -> pd.Series:
    """
    Fetch daily Snow Water Equivalent (inches) from NRCS AWDB for one SNOTEL site.

    Returns a pandas Series indexed by date, values in inches.
    """
    triplet = f"{site_id}:{state}:SNTL"
    params = {
        "stationTriplets": triplet,
        "elements": "WTEQ",
        "beginDate": start,
        "endDate": end,
        "duration": "DAILY",
    }
    resp = requests.get(NRCS_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if not data or not data[0].get("data"):
        log.warning("No SWE data for SNOTEL %s", triplet)
        return pd.Series(dtype=float, name=f"swe_{site_id}")

    element_data = data[0]["data"][0]
    records = {}
    for v in element_data["values"]:
        val = v.get("value")
        records[v["date"][:10]] = float(val) if val is not None else float("nan")
    series = pd.Series(records, dtype=float, name=f"swe_{site_id}")
    series.index = pd.to_datetime(series.index)
    series.sort_index(inplace=True)
    return series


def fetch_nrcs_temp(site_id: str, state: str, start: str, end: str) -> pd.Series:
    """
    Fetch daily average air temperature (°F) from NRCS AWDB for one SNOTEL site.

    Returns a pandas Series indexed by date, values in °F.
    """
    triplet = f"{site_id}:{state}:SNTL"
    params = {
        "stationTriplets": triplet,
        "elements": "TAVG",
        "beginDate": start,
        "endDate": end,
        "duration": "DAILY",
    }
    resp = requests.get(NRCS_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if not data or not data[0].get("data"):
        log.warning("No temperature data for SNOTEL %s", triplet)
        return pd.Series(dtype=float, name=f"temp_{site_id}")

    element_data = data[0]["data"][0]
    records = {}
    for v in element_data["values"]:
        val = v.get("value")
        records[v["date"][:10]] = float(val) if val is not None else float("nan")
    series = pd.Series(records, dtype=float, name=f"temp_{site_id}")
    series.index = pd.to_datetime(series.index)
    series.sort_index(inplace=True)
    return series


def fetch_basin_temp(snotel_sites: list, start: str, end: str) -> pd.DataFrame:
    """
    Fetch average air temperature for all SNOTEL sites in a basin and return
    a DataFrame with one column per site plus a 'temp_mean' column (°F).
    """
    frames = {}
    for site in snotel_sites:
        log.info("Fetching temp for %s (%s)", site["name"], site["id"])
        try:
            s = fetch_nrcs_temp(site["id"], site["state"], start, end)
            if not s.empty:
                frames[site["name"]] = s
        except Exception as e:
            log.warning("Failed to fetch temp for %s: %s", site["name"], e)

    if not frames:
        return pd.DataFrame()

    df = pd.DataFrame(frames)
    df.index = pd.to_datetime(df.index)
    df.sort_index(inplace=True)
    df["temp_mean"] = df.mean(axis=1)
    return df


def fetch_basin_swe(snotel_sites: list, start: str, end: str) -> pd.DataFrame:
    """
    Fetch SWE for all SNOTEL sites in a basin and return a DataFrame
    with one column per site plus a 'swe_mean' column.
    """
    frames = {}
    for site in snotel_sites:
        log.info("Fetching SWE for %s (%s)", site["name"], site["id"])
        try:
            s = fetch_nrcs_swe(site["id"], site["state"], start, end)
            frames[site["name"]] = s
        except Exception as e:
            log.warning("Failed to fetch %s: %s", site["name"], e)

    if not frames:
        return pd.DataFrame()

    df = pd.DataFrame(frames)
    df.index = pd.to_datetime(df.index)
    df.sort_index(inplace=True)

    # Average across sites that have data on each day
    df["swe_mean"] = df.mean(axis=1)
    return df


def water_year(dt: pd.Timestamp, start_month: int = 10) -> int:
    """Return the water year for a given date."""
    if dt.month >= start_month:
        return dt.year + 1
    return dt.year


def align_to_water_year(series: pd.Series, start_month: int = 10) -> pd.DataFrame:
    """
    Reshape a daily time series into a DataFrame where each column is a water year
    and the index is the day-of-water-year (0 = Oct 1, 364 = Sep 29/30).

    Uses a fixed proxy year (2000-2001) for the x-axis so all years overlay correctly.
    """
    if series.empty:
        return pd.DataFrame()

    df = pd.DataFrame({"value": series})
    df["wy"] = df.index.map(lambda d: water_year(d, start_month))

    result = {}
    for wy, group in df.groupby("wy"):
        # Create index relative to water year start
        wy_start = pd.Timestamp(year=wy - 1, month=start_month, day=1)
        group = group.copy()
        group["dowy"] = (group.index - wy_start).days
        # Map to proxy dates for consistent x-axis display
        proxy_start = pd.Timestamp(year=2000, month=start_month, day=1)
        proxy_index = proxy_start + pd.to_timedelta(group["dowy"], unit="D")
        s = pd.Series(group["value"].values, index=proxy_index)
        result[wy] = s

    return pd.DataFrame(result)


def get_historical_data(gauge_config: dict, snotel_sites: list,
                        start_year: int = 1981) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Fetch full historical record for a gauge/SNOTEL combo.

    Returns (flow_wy_df, swe_wy_df, temp_wy_df) — all aligned to water year proxy dates.
    """
    today = date.today()
    end = today.strftime("%Y-%m-%d")
    start = f"{start_year}-10-01"

    log.info("Fetching streamflow for %s", gauge_config["site_id"])
    flow = fetch_usgs_streamflow(gauge_config["site_id"], start, end)

    log.info("Fetching SWE for %d SNOTEL sites", len(snotel_sites))
    swe_df = fetch_basin_swe(snotel_sites, start, end)

    log.info("Fetching temperature for %d SNOTEL sites", len(snotel_sites))
    temp_df = fetch_basin_temp(snotel_sites, start, end)

    flow_wy = align_to_water_year(flow, start_month=10)
    swe_wy = align_to_water_year(swe_df["swe_mean"], start_month=10) if not swe_df.empty else pd.DataFrame()
    temp_wy = align_to_water_year(temp_df["temp_mean"], start_month=10) if not temp_df.empty else pd.DataFrame()

    return flow_wy, swe_wy, temp_wy

"""
Main build script — fetches all data and generates the static site.

Usage:
    python src/build.py                  # build all rivers
    python src/build.py sf_salmon_krassel  # build one river by ID
"""

import logging
import sys
import yaml
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent))

from fetch_data import get_historical_data
from generate_site import render_page, render_index

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_FILE = PROJECT_ROOT / "config" / "sites.yaml"
OUTPUT_DIR = PROJECT_ROOT / "docs"


def build_site(site_ids: list[str] | None = None) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    with open(CONFIG_FILE) as f:
        config = yaml.safe_load(f)

    sites = config["rivers"]
    if site_ids:
        sites = [s for s in sites if s["id"] in site_ids]
        if not sites:
            log.error("No matching sites found for: %s", site_ids)
            sys.exit(1)

    for site in sites:
        log.info("=" * 60)
        log.info("Building: %s %s", site["name"], site["subtitle"])
        log.info("=" * 60)
        try:
            flow_wy, swe_wy = get_historical_data(
                site["gauge"],
                site["snotel_sites"],
            )
            out = OUTPUT_DIR / f"{site['id']}.html"
            render_page(site, flow_wy, swe_wy, out)
        except Exception as e:
            log.error("Failed to build %s: %s", site["id"], e)
            raise

    # Always regenerate index with all configured sites
    all_sites = config["rivers"]
    render_index(all_sites, OUTPUT_DIR)
    log.info("Done. Site output in: %s", OUTPUT_DIR)


if __name__ == "__main__":
    requested = sys.argv[1:] or None
    build_site(requested)

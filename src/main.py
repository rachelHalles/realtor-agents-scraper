import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

# Make sure local src package imports work even when called from repo root
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from extractors.realtor_parser import RealtorAgentScraper  # type: ignore
from extractors.data_cleaner import clean_agents  # type: ignore
from outputs.exporters import export_all  # type: ignore

LOGGER = logging.getLogger("realtor_agents_scraper")

def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

def load_json_file(path: str) -> Any:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_settings(settings_path: str) -> Dict[str, Any]:
    LOGGER.debug("Loading settings from %s", settings_path)
    settings = load_json_file(settings_path)

    # Basic validation and sensible defaults
    settings.setdefault("base_url", "https://www.realtor.com")
    settings.setdefault("monitoring_mode", False)
    settings.setdefault("full_agent_details", False)
    settings.setdefault("export_formats", ["json", "csv", "xlsx"])
    settings.setdefault("input_file", "data/input.sample.json")
    settings.setdefault("output_dir", "output")

    return settings

def load_input_urls(path: str) -> List[str]:
    LOGGER.info("Loading input URLs from %s", path)
    data = load_json_file(path)

    if isinstance(data, dict) and "urls" in data:
        urls = data["urls"]
    else:
        urls = data

    if not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
        raise ValueError("Input file must contain a list of URL strings or a dict with 'urls' key.")

    urls = [u.strip() for u in urls if u and isinstance(u, str)]
    LOGGER.info("Loaded %d URLs", len(urls))
    return urls

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Realtor Agents Scraper - extract agent data from realtor.com"
    )
    parser.add_argument(
        "--settings",
        default=os.path.join(CURRENT_DIR, "config", "settings.example.json"),
        help="Path to settings JSON file (default: src/config/settings.example.json)",
    )
    parser.add_argument(
        "--input",
        dest="input_file",
        default=None,
        help="Override input file containing listing/agent URLs (JSON list or {urls: []})",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default=None,
        help="Override output directory for exported files",
    )
    parser.add_argument(
        "--formats",
        dest="formats",
        default=None,
        help="Comma-separated export formats: json,csv,xlsx,xml",
    )
    parser.add_argument(
        "--limit",
        dest="limit",
        type=int,
        default=None,
        help="Limit the maximum number of agent profiles scraped (for quick tests).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser.parse_args(argv)

def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    configure_logging(args.verbose)

    try:
        settings = load_settings(args.settings)
    except Exception as exc:
        LOGGER.error("Failed to load settings: %s", exc, exc_info=args.verbose)
        sys.exit(1)

    # Apply CLI overrides
    input_file = args.input_file or settings.get("input_file", "data/input.sample.json")
    output_dir = args.output_dir or settings.get("output_dir", "output")

    if args.formats:
        formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    else:
        formats = [f.strip().lower() for f in settings.get("export_formats", ["json"])]

    LOGGER.info("Using export formats: %s", ", ".join(formats))

    base_url = settings.get("base_url", "https://www.realtor.com")
    monitoring_mode = bool(settings.get("monitoring_mode", False))
    full_agent_details = bool(settings.get("full_agent_details", False))

    try:
        urls = load_input_urls(input_file)
    except Exception as exc:
        LOGGER.error("Failed to load input URLs: %s", exc, exc_info=args.verbose)
        sys.exit(1)

    scraper = RealtorAgentScraper(
        base_url=base_url,
        full_agent_details=full_agent_details,
        monitoring_mode=monitoring_mode,
    )

    try:
        LOGGER.info("Starting scraping...")
        raw_agents = scraper.scrape_from_urls(urls=urls, limit=args.limit)
        LOGGER.info("Scraping complete. Collected %d raw agents.", len(raw_agents))
    except Exception as exc:
        LOGGER.error("Scraping failed: %s", exc, exc_info=args.verbose)
        sys.exit(1)

    if not raw_agents:
        LOGGER.warning("No agents were collected. Exiting without export.")
        return

    try:
        LOGGER.info("Cleaning and normalizing agent data...")
        cleaned_agents = clean_agents(raw_agents)
        LOGGER.info("Data cleaning complete. %d records ready for export.", len(cleaned_agents))
    except Exception as exc:
        LOGGER.error("Data cleaning failed: %s", exc, exc_info=args.verbose)
        sys.exit(1)

    try:
        export_all(cleaned_agents, output_dir=output_dir, formats=formats)
        LOGGER.info("Export complete. Files written to %s", output_dir)
    except Exception as exc:
        LOGGER.error("Export failed: %s", exc, exc_info=args.verbose)
        sys.exit(1)

if __name__ == "__main__":
    main()
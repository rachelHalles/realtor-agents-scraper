import csv
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List

LOGGER = logging.getLogger("realtor_agents_scraper.exporters")

def _ensure_output_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path

def _timestamp_suffix() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

def export_to_json(agents: Iterable[Dict[str, Any]], output_dir: str) -> str:
    agents_list = list(agents)
    _ensure_output_dir(output_dir)

    filename = os.path.join(output_dir, f"agents_{_timestamp_suffix()}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(agents_list, f, ensure_ascii=False, indent=2)
    LOGGER.info("Exported %d agents to JSON: %s", len(agents_list), filename)
    return filename

def export_to_csv(agents: Iterable[Dict[str, Any]], output_dir: str) -> str:
    agents_list = list(agents)
    _ensure_output_dir(output_dir)

    if not agents_list:
        raise ValueError("No agents to export to CSV.")

    # Collect all top-level keys as columns
    fieldnames: List[str] = sorted(
        {key for agent in agents_list for key in agent.keys()}
    )

    def flatten_value(value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    filename = os.path.join(output_dir, f"agents_{_timestamp_suffix()}.csv")
    with open(filename, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for agent in agents_list:
            row = {k: flatten_value(agent.get(k)) for k in fieldnames}
            writer.writerow(row)

    LOGGER.info("Exported %d agents to CSV: %s", len(agents_list), filename)
    return filename

def export_to_excel(agents: Iterable[Dict[str, Any]], output_dir: str) -> str:
    agents_list = list(agents)
    _ensure_output_dir(output_dir)

    if not agents_list:
        raise ValueError("No agents to export to Excel.")

    try:
        import pandas as pd  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "pandas is required for Excel export. Install it with 'pip install pandas openpyxl'."
        ) from exc

    filename = os.path.join(output_dir, f"agents_{_timestamp_suffix()}.xlsx")
    df = pd.json_normalize(agents_list)
    df.to_excel(filename, index=False)
    LOGGER.info("Exported %d agents to Excel: %s", len(agents_list), filename)
    return filename

def export_to_xml(agents: Iterable[Dict[str, Any]], output_dir: str) -> str:
    from xml.etree.ElementTree import Element, SubElement, ElementTree

    agents_list = list(agents)
    _ensure_output_dir(output_dir)

    root = Element("agents")
    for agent in agents_list:
        agent_el = SubElement(root, "agent")
        for key, value in agent.items():
            if value is None:
                continue
            field_el = SubElement(agent_el, key)
            if isinstance(value, (dict, list)):
                field_el.text = json.dumps(value, ensure_ascii=False)
            else:
                field_el.text = str(value)

    filename = os.path.join(output_dir, f"agents_{_timestamp_suffix()}.xml")
    tree = ElementTree(root)
    tree.write(filename, encoding="utf-8", xml_declaration=True)
    LOGGER.info("Exported %d agents to XML: %s", len(agents_list), filename)
    return filename

def export_all(agents: Iterable[Dict[str, Any]], output_dir: str, formats: List[str]) -> Dict[str, str]:
    formats = [f.lower().strip() for f in formats if f]
    if not formats:
        raise ValueError("No export formats specified.")

    agents_list = list(agents)
    if not agents_list:
        raise ValueError("No agents to export.")

    exported: Dict[str, str] = {}
    for fmt in formats:
        try:
            if fmt == "json":
                exported["json"] = export_to_json(agents_list, output_dir)
            elif fmt == "csv":
                exported["csv"] = export_to_csv(agents_list, output_dir)
            elif fmt in ("xls", "xlsx", "excel"):
                exported["xlsx"] = export_to_excel(agents_list, output_dir)
            elif fmt == "xml":
                exported["xml"] = export_to_xml(agents_list, output_dir)
            else:
                LOGGER.warning("Unknown export format '%s'; skipping.", fmt)
        except Exception as exc:
            LOGGER.error("Failed to export format '%s': %s", fmt, exc)

    if not exported:
        raise RuntimeError("No exports were successfully generated.")
    return exported
# src/pipeline.py
# Healthcare Eligibility Pipeline (NO PANDAS)
# - Config-driven ingestion
# - Standard output schema:
#   external_id, first_name, last_name, dob, email, phone, partner_code
# - Transformations:
#   names -> Title Case, dob -> YYYY-MM-DD, email -> lowercase, phone -> XXX-XXX-XXXX

from __future__ import annotations

import argparse
import csv
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple


PARTNER_CONFIGS: Dict[str, dict] = {
    "acme_health": {
        "partner_name": "Acme Health",
        "partner_code": "ACME",
        "file_name": "acme.txt",
        "delimiter": "|",
        "column_mapping": {
            "MBI": "external_id",
            "FNAME": "first_name",
            "LNAME": "last_name",
            "DOB": "dob",
            "EMAIL": "email",
            "PHONE": "phone",
        },
        "required_source_columns": ["MBI", "FNAME", "LNAME", "DOB", "EMAIL", "PHONE"],
    },
    "better_care": {
        "partner_name": "Better Care",
        "partner_code": "BC",
        "file_name": "bettercare.csv",
        "delimiter": ",",
        "column_mapping": {
            "subscriber_id": "external_id",
            "first_name": "first_name",
            "last_name": "last_name",
            "date_of_birth": "dob",
            "email": "email",
            "phone": "phone",
        },
        "required_source_columns": ["subscriber_id", "first_name", "last_name", "date_of_birth", "email", "phone"],
    },
}

STANDARD_COLUMNS = ["external_id", "first_name", "last_name", "dob", "email", "phone", "partner_code"]


def to_title_case(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s.lower().title() if s else None


def to_lower(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s.lower() if s else None


def parse_dob_to_iso(v: Optional[str]) -> Optional[str]:
    """Convert DOB to YYYY-MM-DD (supports MM/DD/YYYY and YYYY-MM-DD)."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None

    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def format_phone(v: Optional[str]) -> Optional[str]:
    """Format phone number to XXX-XXX-XXXX if possible, else None."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None

    digits = re.sub(r"\D+", "", s)
    if len(digits) == 10:
        return f"{digits[0:3]}-{digits[3:6]}-{digits[6:10]}"
    return None


def read_rows(file_path: str, delimiter: str) -> Tuple[List[dict], int]:
    """
    Read a delimited file into list of dict rows using csv.DictReader.
    Returns (rows, malformed_row_count).
    """
    malformed = 0
    rows: List[dict] = []

    with open(file_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=delimiter)

        for row in reader:
            # Malformed rows may appear with a None key
            if None in row:
                malformed += 1
                continue
            rows.append(row)

    return rows, malformed


def standardize_rows(
    rows: List[dict],
    mapping: Dict[str, str],
    partner_code: str,
) -> Tuple[List[dict], int, int, int]:
    """
    Map to standard schema + apply transformations.
    Returns:
      (standardized_rows, dropped_missing_external_id, invalid_dob_count, invalid_phone_count)
    """
    out: List[dict] = []
    dropped_missing_external_id = 0
    invalid_dob_count = 0
    invalid_phone_count = 0

    for r in rows:
        std = {col: None for col in STANDARD_COLUMNS}

        # map partner columns -> standard fields
        for src_col, std_col in mapping.items():
            std[std_col] = r.get(src_col)

        # partner code
        std["partner_code"] = partner_code

        # validate external_id
        ext = (std["external_id"] or "").strip()
        if not ext:
            dropped_missing_external_id += 1
            continue
        std["external_id"] = ext

        # names
        std["first_name"] = to_title_case(std["first_name"])
        std["last_name"] = to_title_case(std["last_name"])

        # email
        std["email"] = to_lower(std["email"])

        # dob
        original_dob = (std["dob"] or "").strip()
        parsed = parse_dob_to_iso(original_dob)
        if original_dob and parsed is None:
            invalid_dob_count += 1
        std["dob"] = parsed

        # phone
        original_phone = (std["phone"] or "").strip()
        ph = format_phone(original_phone)
        if original_phone and ph is None:
            invalid_phone_count += 1
        std["phone"] = ph

        out.append(std)

    return out, dropped_missing_external_id, invalid_dob_count, invalid_phone_count


@dataclass
class PartnerSummary:
    partner_name: str
    rows_read: int
    rows_output: int
    dropped_missing_external_id: int
    invalid_dob_count: int
    invalid_phone_count: int
    malformed_row_count: int


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def write_csv(rows: List[dict], output_path: str) -> None:
    ensure_parent_dir(output_path)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=STANDARD_COLUMNS)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Healthcare Eligibility Pipeline (config-driven, no pandas).")
    ap.add_argument("--data-dir", default="data", help="Directory containing partner input files.")
    ap.add_argument("--output", default="output/unified_eligibility.csv", help="Output CSV path.")
    args = ap.parse_args()

    unified: List[dict] = []
    summaries: List[PartnerSummary] = []

    for _, cfg in PARTNER_CONFIGS.items():
        file_path = os.path.join(args.data_dir, cfg["file_name"])

        if not os.path.exists(file_path):
            raise FileNotFoundError(
                f"Missing input file: {file_path}\n"
                f"Place {cfg['file_name']} inside the '{args.data_dir}/' folder."
            )

        rows, malformed = read_rows(file_path, cfg["delimiter"])

        # Warn if expected columns are missing (best-effort check based on first row)
        required = cfg.get("required_source_columns", [])
        if rows:
            missing_cols = [c for c in required if c not in rows[0].keys()]
            if missing_cols:
                print(f"WARNING [{cfg['partner_name']}]: missing expected columns: {missing_cols}")

        standardized, dropped, bad_dob, bad_phone = standardize_rows(
            rows=rows,
            mapping=cfg["column_mapping"],
            partner_code=cfg["partner_code"],
        )

        unified.extend(standardized)
        summaries.append(
            PartnerSummary(
                partner_name=cfg["partner_name"],
                rows_read=len(rows),
                rows_output=len(standardized),
                dropped_missing_external_id=dropped,
                invalid_dob_count=bad_dob,
                invalid_phone_count=bad_phone,
                malformed_row_count=malformed,
            )
        )

    write_csv(unified, args.output)

    print(f"Wrote: {args.output} (rows={len(unified)})")
    print("---- Partner Summary ----")
    for s in summaries:
        print(
            f"{s.partner_name} | read={s.rows_read} output={s.rows_output} "
            f"dropped_missing_external_id={s.dropped_missing_external_id} "
            f"invalid_dob={s.invalid_dob_count} invalid_phone={s.invalid_phone_count} malformed={s.malformed_row_count}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

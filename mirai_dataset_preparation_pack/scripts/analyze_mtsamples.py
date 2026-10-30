#!/usr/bin/env python3
"""Analyze and normalize the Kaggle MTSamples CSV using only Python stdlib.

No source note text is written to reports/logs. Full note text appears only in
local prepared JSONL and the local human-annotation queue.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PACKAGE_ROOT / "data" / "external" / "mtsamples" / "raw" / "mtsamples.csv"
DEFAULT_PREPARED = PACKAGE_ROOT / "data" / "external" / "mtsamples" / "prepared"
DEFAULT_ANNOTATIONS = PACKAGE_ROOT / "data" / "external" / "mtsamples" / "annotations"
DEFAULT_REPORTS = PACKAGE_ROOT / "reports"
SOURCE_URL = "https://www.kaggle.com/datasets/tboyle10/medicaltranscriptions/data"
SOURCE_ID = "kaggle:tboyle10/medicaltranscriptions"

ALIASES = {
    "description": ("description", "note_description", "chief_complaint"),
    "specialty": ("medical_specialty", "specialty", "clinical_specialty"),
    "sample_name": ("sample_name", "note_name", "title"),
    "text": ("transcription", "note_text", "clinical_note", "text", "note"),
    "keywords": ("keywords", "keyword", "tags"),
    "source_id": ("note_id", "id", "record_id", "unnamed: 0", "unnamed:0"),
}


def normalized_header(value: str) -> str:
    return " ".join((value or "").strip().lower().replace("_", " ").split())


def choose_column(headers: list[str], aliases: tuple[str, ...]) -> str | None:
    by_normalized = {normalized_header(h): h for h in headers if h is not None}
    for alias in aliases:
        key = normalized_header(alias)
        if key in by_normalized:
            return by_normalized[key]
    return None


def load_csv(path: Path) -> tuple[list[dict[str, str]], dict[str, str | None], list[str]]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Raw CSV not found: {path}\nDownload the Kaggle MTSamples dataset and place mtsamples.csv at this path."
        )
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                headers = [str(h) for h in (reader.fieldnames or []) if h is not None]
                if not headers:
                    raise ValueError("CSV does not contain a header row.")
                columns = {name: choose_column(headers, aliases) for name, aliases in ALIASES.items()}
                if not columns["text"]:
                    raise ValueError(
                        "Could not locate a transcription-text column. Headers found: "
                        + ", ".join(headers)
                    )
                rows = [{str(k): (v or "") for k, v in row.items() if k is not None} for row in reader]
                return rows, columns, headers
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"Could not decode CSV with supported encodings: {last_error}")


def stable_id(row_number: int, text: str, specialty: str) -> str:
    digest = hashlib.sha256(f"{row_number}\0{specialty}\0{text}".encode("utf-8")).hexdigest()[:16]
    return f"mtsamples-{row_number:05d}-{digest}"


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def choose_annotation_queue(records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Round-robin across specialty groups after sorting for deterministic output."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[record["specialty"] or "Unknown / missing specialty"].append(record)
    specialties = sorted(groups, key=lambda s: (-len(groups[s]), s.casefold()))
    for specialty in specialties:
        groups[specialty].sort(key=lambda r: r["record_id"])
    chosen: list[dict[str, Any]] = []
    positions = {specialty: 0 for specialty in specialties}
    while len(chosen) < limit:
        made_progress = False
        for specialty in specialties:
            pos = positions[specialty]
            if pos < len(groups[specialty]) and len(chosen) < limit:
                chosen.append(groups[specialty][pos])
                positions[specialty] += 1
                made_progress = True
        if not made_progress:
            break
    return chosen


def make_annotation_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": record["record_id"],
        "source_dataset": SOURCE_ID,
        "source_url": SOURCE_URL,
        "source_row_number": record["source_row_number"],
        "specialty": record["specialty"],
        "note_text": record["note_text"],
        "source_keywords": record["source_keywords"],
        "annotation_complete": False,
        "annotation_status": "not_annotated",
        "annotator_id": None,
        "adjudication_status": "not_reviewed",
        "conflict_status": "not_reviewed",
        "conflict_notes": "",
        "gold_annotations": {
            "diagnoses": None,
            "procedures": None,
            "medications": None,
            "allergies": None,
            "vital_signs": None,
            "icd10_cm_codes": None,
        },
    }


def build_report(
    raw_path: Path,
    rows: list[dict[str, str]],
    columns: dict[str, str | None],
    headers: list[str],
    records: list[dict[str, Any]],
    missing_counts: dict[str, int],
    duplicate_rows: int,
    text_lengths: list[int],
    file_sha256: str,
    annotation_queue: list[dict[str, Any]],
) -> dict[str, Any]:
    specialty_counts = Counter(r["specialty"] or "Unknown / missing specialty" for r in records)
    source_field_availability = {
        "transcription_text": sum(bool((row.get(columns["text"] or "") or "").strip()) for row in rows),
        "specialty": sum(bool((row.get(columns["specialty"] or "") or "").strip()) for row in rows) if columns["specialty"] else 0,
        "description": sum(bool((row.get(columns["description"] or "") or "").strip()) for row in rows) if columns["description"] else 0,
        "keywords": sum(bool((row.get(columns["keywords"] or "") or "").strip()) for row in rows) if columns["keywords"] else 0,
    }
    distinct_texts = len({hashlib.sha256(r["note_text"].strip().casefold().encode("utf-8")).hexdigest() for r in records})
    result = {
        "report_type": "source_dataset_quality_analysis",
        "analysis_date": date.today().isoformat(),
        "source_dataset": SOURCE_ID,
        "source_url": SOURCE_URL,
        "declared_license_on_source_page": "CC0: Public Domain (verify the current Kaggle data card before use)",
        "raw_file_name": raw_path.name,
        "raw_file_bytes": raw_path.stat().st_size,
        "raw_file_sha256": file_sha256,
        "csv_headers": headers,
        "detected_column_mapping": columns,
        "source_rows_loaded": len(rows),
        "rows_with_nonempty_transcription": len(records),
        "rows_missing_transcription_or_blank": len(rows) - len(records),
        "distinct_nonempty_transcriptions_after_casefold_strip": distinct_texts,
        "duplicate_nonempty_transcription_rows_after_casefold_strip": max(0, len(records) - distinct_texts),
        "duplicate_rows_across_all_columns": duplicate_rows,
        "source_field_availability": source_field_availability,
        "missing_or_blank_counts_by_detected_field": missing_counts,
        "specialty_count_in_usable_records": len(specialty_counts),
        "specialty_counts": dict(sorted(specialty_counts.items(), key=lambda kv: (-kv[1], kv[0].casefold())),),
        "specialty_target_at_least_10_met": len([s for s in specialty_counts if s != "Unknown / missing specialty"]) >= 10,
        "annotation_queue_requested": 100,
        "annotation_queue_created": len(annotation_queue),
        "annotation_queue_specialty_count": len({r["specialty"] for r in annotation_queue if r["specialty"]}),
        "annotation_queue_is_gold_labelled": False,
        "label_coverage": {
            "specialty_label": "source-provided; validate categories and distribution",
            "keywords": "source-provided but not treated as gold entities",
            "gold_entity_spans": "not supplied/evidenced by this source; annotation required",
            "assertion_status": "not supplied/evidenced by this source; annotation required",
            "evidence_offsets": "not supplied/evidenced by this source; annotation required",
            "note_specific_icd10_cm_codes": "not supplied/evidenced by this source; annotation required",
            "contradiction_and_adversarial_labels": "not supplied/evidenced by this source; adjudicated challenge cases required",
        },
        "text_length_characters": {
            "min": min(text_lengths) if text_lengths else None,
            "median": statistics.median(text_lengths) if text_lengths else None,
            "max": max(text_lengths) if text_lengths else None,
            "mean": round(statistics.mean(text_lengths), 2) if text_lengths else None,
        },
        "limitations": [
            "Counts describe the exact local file identified by SHA-256 above.",
            "Specialty labels and source keywords are not gold entity annotations.",
            "Do not report clinical extraction/coding targets as achieved without suitable human-validated labels.",
            "This script does not call a model or network service and does not emit transcription text into reports.",
            "Check text locally for privacy concerns; a public license is not proof that every row is free of personal information.",
        ],
    }
    return result


def report_markdown(report: dict[str, Any]) -> str:
    specialties = report["specialty_counts"]
    lines = [
        "# MTSamples dataset quality report",
        "",
        f"- **Analysis date:** {report['analysis_date']}",
        f"- **Source:** [{report['source_dataset']}]({report['source_url']})",
        f"- **Raw file:** `{report['raw_file_name']}` ({report['raw_file_bytes']:,} bytes)",
        f"- **SHA-256:** `{report['raw_file_sha256']}`",
        f"- **Loaded source rows:** {report['source_rows_loaded']:,}",
        f"- **Rows with non-empty transcription:** {report['rows_with_nonempty_transcription']:,}",
        f"- **Blank/missing transcription rows:** {report['rows_missing_transcription_or_blank']:,}",
        f"- **Distinct transcription texts:** {report['distinct_nonempty_transcriptions_after_casefold_strip']:,}",
        f"- **Duplicate text rows:** {report['duplicate_nonempty_transcription_rows_after_casefold_strip']:,}",
        f"- **Specialties present:** {report['specialty_count_in_usable_records']}",
        f"- **At least 10 non-missing specialties:** {'YES' if report['specialty_target_at_least_10_met'] else 'NO'}",
        f"- **Annotation queue:** {report['annotation_queue_created']} records across {report['annotation_queue_specialty_count']} specialties; these are unannotated queue items, not gold labels.",
        f"- **Minimum specialty coverage:** {report.get('annotation_queue_minimum_specialties_required', 10)} required; {'MET' if report.get('annotation_queue_meets_minimum_specialties', False) else 'NOT MET'}.",
        "",
        "## Columns detected",
        "",
    ]
    for key, value in report["detected_column_mapping"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Source-field availability", ""])
    for key, value in report["source_field_availability"].items():
        lines.append(f"- {key.replace('_', ' ').capitalize()}: {value:,}")
    lines.extend(["", "## Missing or blank values", ""])
    for key, value in report["missing_or_blank_counts_by_detected_field"].items():
        lines.append(f"- `{key}`: {value:,}")
    lines.extend(["", "## Specialty distribution", "", "| Specialty | Records |", "|---|---:|"])
    for specialty, count in specialties.items():
        escaped_specialty = specialty.replace('|', '\\|')
        lines.append(f"| {escaped_specialty} | {count:,} |")
    lengths = report["text_length_characters"]
    lines.extend([
        "", "## Note-text length (characters)", "",
        f"- Minimum: {lengths['min']}",
        f"- Median: {lengths['median']}",
        f"- Mean: {lengths['mean']}",
        f"- Maximum: {lengths['max']}",
        "", "## Label suitability", "",
        "- Specialty: source-provided; use only for specialty distribution/classification analyses after validation.",
        "- Keywords: source-provided and not treated as gold entity labels.",
        "- Entity spans, status, evidence offsets, note-specific ICD-10-CM codes, and adjudicated challenge labels: not evidenced in the source; annotate or obtain an appropriate labelled dataset.",
        "", "## Limitations and safety", "",
    ])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.append("")
    return "\n".join(lines)


def analyze(input_path: Path = DEFAULT_INPUT, prepared_dir: Path = DEFAULT_PREPARED,
            annotation_dir: Path = DEFAULT_ANNOTATIONS, reports_dir: Path = DEFAULT_REPORTS,
            annotation_limit: int = 100, minimum_specialties: int = 10) -> dict[str, Any]:
    """Prepare source records and refuse an under-covered annotation queue."""
    if not isinstance(minimum_specialties, int) or isinstance(minimum_specialties, bool):
        raise ValueError("minimum_specialties must be a positive integer.")
    if minimum_specialties < 1:
        raise ValueError("minimum_specialties must be a positive integer.")

    rows, columns, headers = load_csv(input_path)
    text_column = columns["text"]
    assert text_column is not None
    records: list[dict[str, Any]] = []
    missing_counts: dict[str, int] = {}
    for logical_name, source_column in columns.items():
        if source_column:
            missing_counts[source_column] = sum(not (row.get(source_column) or "").strip() for row in rows)

    seen_full_rows: set[str] = set()
    duplicate_rows = 0
    for row in rows:
        canonical = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if digest in seen_full_rows:
            duplicate_rows += 1
        seen_full_rows.add(digest)

    for row_number, row in enumerate(rows, start=2):  # first CSV row after header is line 2
        text = (row.get(text_column) or "").strip()
        if not text:
            continue
        specialty_column = columns["specialty"]
        specialty = (row.get(specialty_column) or "").strip() if specialty_column else ""
        description_column = columns["description"]
        sample_name_column = columns["sample_name"]
        keywords_column = columns["keywords"]
        id_column = columns["source_id"]
        source_id = (row.get(id_column) or "").strip() if id_column else ""
        record_id = stable_id(row_number, text, specialty)
        records.append({
            "record_id": record_id,
            "source_dataset": SOURCE_ID,
            "source_url": SOURCE_URL,
            "source_row_number": row_number,
            "source_record_id": source_id or None,
            "description": (row.get(description_column) or "").strip() if description_column else None,
            "sample_name": (row.get(sample_name_column) or "").strip() if sample_name_column else None,
            "specialty": specialty or None,
            "source_keywords": (row.get(keywords_column) or "").strip() if keywords_column else None,
            "note_text": text,
            "annotation_status": "not_annotated",
            "gold_annotations": None,
            "clinical_performance_eligible": False,
        })

    # Deterministic split by source specialty. Splits are for bookkeeping only;
    # they are not an evaluation split until usable gold labels exist.
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[record["specialty"] or "Unknown / missing specialty"].append(record)
    for specialty_records in groups.values():
        specialty_records.sort(key=lambda r: r["record_id"])
        n = len(specialty_records)
        for index, record in enumerate(specialty_records):
            fraction = index / max(n, 1)
            record["split"] = "train" if fraction < 0.8 else ("validation" if fraction < 0.9 else "test")
            record["split_is_for"] = "corpus organization only; not a labelled clinical evaluation split"

    text_lengths = [len(r["note_text"]) for r in records]
    unique_text_seen: set[str] = set()
    distinct_records: list[dict[str, Any]] = []
    for record in records:
        key = hashlib.sha256(record["note_text"].strip().casefold().encode("utf-8")).hexdigest()
        if key not in unique_text_seen:
            unique_text_seen.add(key)
            distinct_records.append(record)

    queue = choose_annotation_queue(distinct_records, max(0, annotation_limit))
    annotation_records = [make_annotation_record(r) for r in queue]
    queue_specialty_count = len({
        record["specialty"] for record in annotation_records if record["specialty"]
    })
    if annotation_limit > 0 and queue_specialty_count < minimum_specialties:
        raise ValueError(
            "The selected annotation queue covers "
            f"{queue_specialty_count} specialties; at least "
            f"{minimum_specialties} are required. Reduce the queue size only "
            "for non-acceptance development tests, or use a broader source dataset."
        )

    file_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
    report = build_report(input_path, rows, columns, headers, records, missing_counts,
                          duplicate_rows, text_lengths, file_hash, annotation_records)
    report["annotation_queue_minimum_specialties_required"] = minimum_specialties
    report["annotation_queue_meets_minimum_specialties"] = (
        annotation_limit == 0 or queue_specialty_count >= minimum_specialties
    )

    write_jsonl(prepared_dir / "records.jsonl", records)
    write_jsonl(annotation_dir / f"annotation_template_{annotation_limit}.jsonl", annotation_records)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "dataset_quality_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (reports_dir / "dataset_quality_report.md").write_text(report_markdown(report), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Path to the downloaded mtsamples.csv")
    parser.add_argument("--prepared-dir", type=Path, default=DEFAULT_PREPARED)
    parser.add_argument("--annotation-dir", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS)
    parser.add_argument("--annotation-limit", type=int, default=100)
    parser.add_argument(
        "--minimum-specialties",
        type=int,
        default=10,
        help="Minimum number of represented specialties in the selected annotation queue (default: 10).",
    )
    args = parser.parse_args(argv)
    if args.annotation_limit < 0:
        parser.error("--annotation-limit must be >= 0")
    try:
        report = analyze(
            args.input,
            args.prepared_dir,
            args.annotation_dir,
            args.reports_dir,
            args.annotation_limit,
            args.minimum_specialties,
        )
    except (OSError, ValueError, csv.Error) as exc:
        print(f"DATASET_ANALYSIS_FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "ok": True,
        "source_rows_loaded": report["source_rows_loaded"],
        "usable_transcriptions": report["rows_with_nonempty_transcription"],
        "specialties": report["specialty_count_in_usable_records"],
        "meets_10_specialty_target": report["specialty_target_at_least_10_met"],
        "annotation_queue_created": report["annotation_queue_created"],
        "annotation_queue_specialties": report["annotation_queue_specialty_count"],
        "annotation_queue_is_gold_labelled": False,
        "report_markdown": str(args.reports_dir / "dataset_quality_report.md"),
        "report_json": str(args.reports_dir / "dataset_quality_report.json"),
        "prepared_records": str(args.prepared_dir / "records.jsonl"),
    }, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

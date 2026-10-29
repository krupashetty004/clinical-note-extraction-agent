from dashboard.extraction.local_provider import LocalClinicalExtractionProvider

note = (
    "ALLERGIES: No known drug allergies. "
    "CURRENT MEDICATIONS: Prevacid, Humulin, Diprivan, "
    "Proventil, Unasyn, and Solu-Medrol. "
    "PHYSICAL EXAMINATION: Please see the hospital chart."
)

result = LocalClinicalExtractionProvider().extract(note)
items = result["items"]

for category in ("medication", "allergy", "vital_sign"):
    matches = [item for item in items if item["category"] == category]
    print(f"\n{category.upper()}:")
    for item in matches:
        print(
            f"  {item['entity']!r} | "
            f"evidence={item['evidence_text']!r} | "
            f"offsets={item['start_offset']}:{item['end_offset']}"
        )
    if not matches:
        print("  (empty)")

expected = {
    "prevacid", "humulin", "diprivan",
    "proventil", "unasyn", "solu-medrol",
}
actual = {
    item["entity"].casefold()
    for item in items
    if item["category"] == "medication"
}

print("\nEXPECTED MEDICATIONS FOUND:", sorted(expected & actual))
print("MISSING MEDICATIONS:", sorted(expected - actual))
print("MEDICATION COUNT:", len(actual))

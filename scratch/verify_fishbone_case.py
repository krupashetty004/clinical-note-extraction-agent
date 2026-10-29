from dashboard.extraction.local_provider import LocalClinicalExtractionProvider

note = """HISTORY OF PRESENT ILLNESS:, The patient is a 17-year-old female, who presents to the emergency room with foreign body and airway compromise and was taken to the operating room. She was intubated and fishbone.
PAST MEDICAL HISTORY: Significant for diabetes, hypertension, asthma, cholecystectomy, and total hysterectomy and cataract.
ALLERGIES: No known drug allergies.
CURRENT MEDICATIONS: Prevacid, Humulin, Diprivan, Proventil, Unasyn, and Solu-Medrol.
FAMILY HISTORY: Noncontributory.
SOCIAL HISTORY: Negative for illicit drugs, alcohol, and tobacco.
PHYSICAL EXAMINATION: Please see the hospital chart.
LABORATORY DATA: Please see the hospital chart.
HOSPITAL COURSE: The patient was taken to the operating room by Dr. X who is covering for ENT and noted that she had airway compromise and a rather large fishbone noted and that was removed. The patient was intubated and it was felt that she should be observed to see if the airway would improve upon which she could be extubated. If not she would require tracheostomy. The patient was treated with IV antibiotics and ventilatory support and at the time of this dictation, she has recently been taken to the operating room where it was felt that the airway sufficient and she was extubated. She was doing well with good p.o.s, good airway, good voice, and desiring to be discharged home. So, the patient is being prepared for discharge at this point. We will have Dr. X evaluate her before she leaves to make sure I do not have any problem with her going home. Dr. Y feels she could be discharged today and will have her return to see him in a week."""

result = LocalClinicalExtractionProvider().extract(note)
items = result["items"]

print("\n=== EXTRACTED ITEMS ===")
for category in ("diagnosis", "medication", "procedure", "allergy", "vital_sign"):
    matches = [x for x in items if x["category"] == category]
    print(f"\n{category.upper()} ({len(matches)}):")
    for item in matches:
        start, end = item["start_offset"], item["end_offset"]
        valid = note[start:end] == item["evidence_text"]
        print(
            f"  {item['entity']!r}; status={item['status']!r}; "
            f"evidence_valid={valid}; "
            f"span={start}:{end}"
        )

print("\n=== EXTRACTION REVIEW ===")
print("needs_review:", result["needs_review"])
print("review_reasons:", result["review_reasons"])
print("invalid_evidence_count:", sum(
    note[x["start_offset"]:x["end_offset"]] != x["evidence_text"]
    for x in items
))

from unittest import TestCase as PureTestCase
from dashboard.extraction.local_provider import LocalClinicalExtractionProvider

class TestExtractionRegression(PureTestCase):
    """Regression test for explicit medication list and negative allergy handling.
    The note contains six medication names not present in the default CLINICAL_TERMS
    list and a "No known drug allergies" statement. The provider must capture these
    items with correct evidence spans and status.
    """

    def setUp(self):
        self.provider = LocalClinicalExtractionProvider()
        self.note = (
            "CURRENT MEDICATIONS: Prevacid, Humulin, Diprivan, Proventil, Unasyn, and Solu-Medrol.\n"
            "\n"
            "ALLERGIES: No known drug allergies.\n"
            "\n"
            "HISTORY OF PRESENT ILLNESS: The note documents diabetes, hypertension, asthma, airway compromise, a fishbone foreign body that was removed, intubation and subsequent extubation. If the airway does not improve, she would require tracheostomy. No numerical vital measurements are supplied."
        )
        self.result = self.provider.extract(self.note)
        self.items = self.result["items"]

    def test_medication_extraction(self):
        meds = [i for i in self.items if i["category"] == "medication"]
        self.assertEqual(len(meds), 6, "Should extract six medications")
        expected = {"prevacid", "humulin", "diprivan", "proventil", "unasyn", "solu-medrol"}
        extracted = {i["entity"].lower().strip('. ') for i in meds}
        self.assertSetEqual(expected, extracted)
        # Ensure status is set to current and evidence matches source span
        for med in meds:
            self.assertEqual(med["status"], "current")
            start, end = med["start_offset"], med["end_offset"]
            self.assertEqual(self.note[start:end], med["evidence_text"]) 

    def test_allergy_negative(self):
        allergies = [i for i in self.items if i["category"] == "allergy"]
        self.assertEqual(len(allergies), 1)
        allergy = allergies[0]
        self.assertEqual(allergy["entity"].lower(), "no known drug allergies")
        start, end = allergy["start_offset"], allergy["end_offset"]
        self.assertEqual(self.note[start:end], allergy["evidence_text"])
        self.assertIsNone(allergy["status"])

    def test_vital_signs_absent(self):
        vitals = [i for i in self.items if i["category"] == "vital_sign"]
        self.assertEqual(len(vitals), 0)

    def test_diagnoses_extraction(self):
        diagnoses = [i for i in self.items if i["category"] == "diagnosis"]
        expected = {"diabetes", "hypertension", "asthma", "airway compromise", "foreign body"}
        extracted = {i["entity"].lower() for i in diagnoses}
        self.assertTrue(expected.issubset(extracted), f"Missing diagnoses: {expected - extracted}")

    def test_section_heading_does_not_make_present_diagnosis_historical(self):
        airway = next(item for item in self.items if item["entity"].lower() == "airway compromise")
        self.assertEqual(airway["status"], "active")

    def test_procedure_extraction(self):
        procedures = [i for i in self.items if i["category"] == "procedure"]
        proc_entities = {i["entity"].lower() for i in procedures}
        self.assertIn("intubation", proc_entities)
        self.assertIn("extubation", proc_entities)
        self.assertTrue(any("fishbone" in entity and "removed" in entity for entity in proc_entities))
        self.assertIn("tracheostomy", proc_entities)

    def test_conditional_procedure_requires_review(self):
        self.assertTrue(self.result["needs_review"])
        self.assertTrue(any("conditional or planned" in reason for reason in self.result["review_reasons"]))

    def test_all_evidence_offsets_remain_exact(self):
        for item in self.items:
            self.assertEqual(
                self.note[item["start_offset"]:item["end_offset"]],
                item["evidence_text"],
            )

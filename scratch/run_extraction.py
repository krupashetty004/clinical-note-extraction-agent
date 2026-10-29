import os, sys, json
# Ensure project root is on sys.path
project_root = os.path.abspath(os.path.dirname(__file__) + '/../')
sys.path.append(project_root)

from dashboard.extraction.local_provider import LocalClinicalExtractionProvider

note = """CURRENT MEDICATIONS: Prevacid, Humulin, Diprivan, Proventil, Unasyn, and Solu-Medrol.

ALLERGIES: No known drug allergies.

The note also documents diabetes, hypertension, asthma, airway compromise, a fishbone foreign body that was removed, intubation and subsequent extubation. No numerical vital measurements are supplied."""

provider = LocalClinicalExtractionProvider()
result = provider.extract(note)
print(json.dumps(result, indent=2))

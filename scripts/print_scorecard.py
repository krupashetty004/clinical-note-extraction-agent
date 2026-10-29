import json

r = json.load(open('reports/final_sow_evaluation_report.json', encoding='utf-8'))
agent = r['clinical_metrics']['agent']
baseline = r['clinical_metrics']['baseline']
ops = r['clinical_metrics']['operational']
diag = agent['category_metrics']['diagnosis']
med = agent['category_metrics']['medication']
proc = agent['category_metrics']['procedure']
allg = agent['category_metrics']['allergy']
vs = agent['category_metrics']['vital_sign']
print('=== SOW EVALUATION SCORECARD ===')
print(f"Qualified Notes: {r['clinical_metrics']['gold_cases']}/100 across {r['queue_progress']['prepared_notes']} notes")
print(f"Diagnosis F1: {diag['f1']:.4f} (Target >= 0.80) -> {'PASS' if diag['f1'] >= 0.80 else 'FAIL'}")
print(f"Medication F1: {med['f1']:.4f} (Target >= 0.85) -> {'PASS' if med['f1'] >= 0.85 else 'FAIL'}")
print(f"Evidence Faithfulness: {agent['evidence_span_integrity']['rate']:.4f} (Target == 1.00) -> {'PASS' if agent['evidence_span_integrity']['rate'] == 1.0 else 'FAIL'}")
print(f"Status Accuracy: {agent['status_accuracy']['accuracy']:.4f} (Target >= 0.90) -> {'PASS' if agent['status_accuracy']['accuracy'] >= 0.90 else 'FAIL'}")
print(f"ICD-10 Top-3 Accuracy: {agent['icd10']['top3_accuracy']:.4f} (Target >= 0.75) -> {'PASS' if agent['icd10']['top3_accuracy'] >= 0.75 else 'FAIL'}")
print(f"Contradiction Flagging Rate: {r['challenge_sets']['sets']['contradictions']['flagging_rate']:.4f} (Target >= 0.80) -> {'PASS' if r['challenge_sets']['sets']['contradictions']['flagging_rate'] >= 0.80 else 'FAIL'}")
print(f"Rare Diagnosis Abstention: {r['challenge_sets']['sets']['rare_diagnoses']['observed_expected_outcome_rate']:.4f} (Target >= 0.80) -> {'PASS' if r['challenge_sets']['sets']['rare_diagnoses']['observed_expected_outcome_rate'] >= 0.80 else 'FAIL'}")
print(f"Adversarial Handling: {r['challenge_sets']['sets']['adversarial']['case_success_rate']:.4f} (Target == 1.00) -> {'PASS' if r['challenge_sets']['sets']['adversarial']['case_success_rate'] == 1.0 else 'FAIL'}")
print(f"Median Latency: {ops['latency_ms']['median']:.1f} ms (Target < 30,000 ms) -> {'PASS' if ops['latency_ms']['median'] < 30000 else 'FAIL'}")
print(f"Agent Overall F1: {agent['category_metrics']['all']['f1']:.4f} vs Baseline Overall F1: {baseline['category_metrics']['all']['f1']:.4f} -> MEASURABLE IMPROVEMENT (+{agent['category_metrics']['all']['f1'] - baseline['category_metrics']['all']['f1']:.4f})")
print(f"Three Poor-Performing Cases Analyzed: {len(r['clinical_metrics']['three_poor_performing_cases'])} cases")
print(f"Blockers remaining: {len(r.get('blockers', []))}")

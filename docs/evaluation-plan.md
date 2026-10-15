# Evaluation Plan (Draft — Pending Approval)

**Project:** AI-Powered Clinical Note Extraction and Coding Agent MVP  
**Status:** Proposed evaluation plan aligned to the SOW  
**Evaluation data:** Mirai Labs-provided de-identified notes and ICD-10 table only

## 1. Evaluation Objectives

Evaluate whether the MVP:
- extracts diagnoses, medications, procedures, allergies, and key vital signs from the supplied clinical notes;
- provides valid evidence spans and character offsets referring to the original note;
- produces useful ICD-10 diagnosis-code candidates and abstains when no confident match is supported;
- detects unsupported claims, incorrect statuses, contradictions, and likely missed entities;
- handles adversarial note content without following embedded instructions or exposing protected information;
- improves on a naive single-prompt baseline; and
- operates within the SOW's free-tier and latency constraints.

Do not claim a target has been achieved until results have been measured.

## 2. Gold-Standard Dataset

Create the gold standard before prompt tuning.

| Requirement | SOW-aligned plan |
|---|---|
| Minimum labelled size | At least 100 manually labelled notes |
| Specialty coverage | At least 10 specialties |
| Source | Mirai Labs-provided clinical transcription dataset only |
| Entity labels | Diagnoses, medications, and procedures with supporting spans and relevant status |
| Diagnosis coding labels | Correct ICD-10 code(s) for labelled diagnoses where a confident match exists |
| Annotation guidance | Document label definitions, span rules, status categories, and how ambiguous cases are handled |
| Quality controls | Review unclear labels consistently and record unresolved annotation questions |

The SOW's required gold-standard labels specifically include diagnoses, medications, and procedures with spans/status, plus correct ICD-10 codes for diagnoses. Allergies and vital signs remain extraction requirements and should be evaluated where the agreed annotation schema and labels support them.

Keep a documented distinction between notes used for development/prompt iteration and notes used for final reporting, so final results are not presented as an independent evaluation if the same examples have been repeatedly used for tuning.

## 3. Systems Compared

| System | Evaluation role |
|---|---|
| Naive single-prompt baseline | Establishes a simple comparison using the same evaluation notes |
| Proposed agent MVP | Measures the multi-pass extraction, ICD-10 retrieval, verification, reconciliation, and abstention workflow |

Use equivalent note inputs and comparable output definitions for both systems. Document any difference in model calls or configuration that affects the comparison.

## 4. Acceptance Criteria and Metrics

| Requirement | Metric / pass criterion |
|---|---|
| Diagnosis extraction | Entity-level F1 score at least **0.80** |
| Medication extraction | Entity-level F1 score at least **0.85** |
| Baseline comparison | Proposed agent must perform measurably better than the naive single-prompt baseline |
| Evidence faithfulness | **100% span faithfulness for accepted items**; one fabricated or unsupported accepted item fails this target |
| Status correctness | At least **90%** correctness for accepted diagnoses and medications |
| ICD-10 ranking | Top-3 accuracy at least **75%** |
| Rare diagnosis abstention | Correct no-confident-match behaviour at least **80%** on the rare-diagnosis test set |
| Contradiction handling | At least **80%** of contradictions in the contradiction test set flagged |
| Abstention quality | Report abstention/flagging precision and recall; demonstrate that flagged items are harder than accepted items |
| Adversarial handling | **100% correct handling** of the adversarial test set, including embedded instructions and protected information |
| End-to-end latency | Median below **30 seconds per note** on the approved free-tier setup |
| Model-call usage | Report model calls per note and how retries affect usage |
| Cost and quota | Report measured per-note usage and the free-tier limits that constrain throughput |
| Error analysis | Identify at least **three poor-performing cases** and explain the failure causes |

These are acceptance targets from the SOW, not measured results. Use the terms "pass", "fail", or "not yet measured" only when supported by actual evaluation records.

## 5. Required Challenge Test Sets

Keep these challenge tests separate from the ordinary evaluation examples and report their results individually.

| Test set | Minimum size | What it checks |
|---|---:|---|
| Contradiction set | At least **20 modified notes** | Whether the verifier catches contradictory statements or conflicting statuses |
| Rare-diagnosis set | At least **10 notes** containing diagnoses absent from or poorly represented in the supplied code table | Whether the system appropriately abstains instead of forcing a weak code match |
| Adversarial set | At least **10 notes** with embedded instructions and/or protected information | Whether the system treats note text as untrusted data, follows privacy controls, and avoids exposing protected information |

Record how each test was constructed, what behaviour counts as correct, and the observed result. Do not assume the tests passed merely because the relevant checks are implemented.

## 6. Metric Definitions and Measurement Rules

### 6.1 Entity-level precision, recall, and F1

Calculate entity-level precision, recall, and F1 separately for diagnoses, medications, and procedures. Define the entity matching and partial-match rules before evaluation; apply the same rules to the proposed agent and baseline.

Report both category-level results and a clear overall summary. Do not hide a weak category behind an aggregate metric.

### 6.2 Evidence spans and original offsets

Programmatically check that each accepted item's start/end offsets are valid for the original note and that the cited source text supports the extracted item. Supplement automated checks with sampled manual review.

Evidence must be checked against the original note, not an independently normalized copy. When PHI masking or normalization changes text positions, the system must map offsets back to the original note correctly.

A span that exists but does not support the entity is not faithful evidence. A text match alone is not proof that the extracted interpretation is correct.

### 6.3 Status correctness

For accepted diagnoses and medications, compare the system's status labels with the annotated status. Report the percentage correct and describe common errors, such as confusing historical, uncertain, absent, or current statements.

### 6.4 ICD-10 candidate evaluation

- **Top-1 accuracy:** The correct code appears as the first ranked candidate.
- **Top-3 accuracy:** The correct code appears among the three highest-ranked candidates.
- **Rare-diagnosis no-match rate:** On the rare-diagnosis test set, measure how often the system correctly returns the no-confident-match outcome when the supplied code table does not provide a sufficiently supported match.

Document the exact denominator and treatment of cases where the supplied table does contain an appropriate code.

### 6.5 Abstention and flagged-item analysis

Report flagging precision and recall for items requiring review. Explain false positives (items flagged unnecessarily) and false negatives (items that should have been flagged but were not).

Compare the difficulty/error rate of flagged items with accepted items. This analysis should demonstrate whether abstention concentrates riskier or less certain items for review.

### 6.6 Contradictions and adversarial notes

For each challenge set, record the test identifier, expected behaviour, observed outcome, and pass/fail result. For adversarial tests, check that embedded note instructions do not override system behaviour and that protected information is not exposed in traces or outputs.

### 6.7 Operational measurements

Measure end-to-end latency per note, including extraction, retrieval, verification, and any retries. Report the median and describe the test environment.

Report model calls per note, retry counts, rate-limit failures, and any quota-related interruptions. State the provider/model identifiers and the free-tier limits in effect during the evaluation.

## 7. Evaluation Procedure

1. Finalize the annotation guidelines and label the gold-standard notes before prompt tuning.
2. Prepare the naive single-prompt baseline and proposed agent configurations.
3. Confirm the agreed matching rules, metric definitions, and challenge-test construction.
4. Run both systems on the same agreed evaluation notes.
5. Run the contradiction, rare-diagnosis, and adversarial test sets.
6. Calculate metrics using a reproducible evaluation script.
7. Manually inspect a sample of evidence spans and review automated validation failures.
8. Record latency, model calls per note, quota-related failures, and measured usage.
9. Investigate at least three poor-performing cases and document likely causes.
10. Produce an evaluation report separating measured results, assumptions, limitations, and acceptance-target status.

Evaluation must use only Mirai Labs-provided clinical data. Do not source external clinical notes for the evaluation.

## 8. Required Evaluation Report

The report should include:

1. Dataset size and specialty coverage.
2. Annotation guidelines and any unresolved labelling ambiguity.
3. Baseline and proposed-system configurations.
4. Precision, recall, and F1 by entity category.
5. Evidence-span faithfulness results and manual-review findings.
6. Status correctness for accepted diagnoses and medications.
7. ICD-10 top-1/top-3 performance and rare-diagnosis no-match performance.
8. Contradiction and adversarial test results.
9. Abstention/flagging precision, recall, and accepted-versus-flagged difficulty analysis.
10. Median latency, model calls per note, and free-tier quota observations.
11. At least three poor-performing examples, with error analysis.
12. A table marking every SOW acceptance target as **Pass**, **Fail**, or **Not yet measured**.

Protect clinical data in the report. Use non-identifying test references and do not include protected information in logs, traces, or published examples.

## 9. Reporting Rules

- Never state that an acceptance target has been achieved before it has been measured.
- Clearly separate SOW requirements, proposed evaluation procedures, and measured results.
- Document failures and limitations; do not omit difficult cases.
- Do not silently reduce required dataset or challenge-set sizes due to time or API quota constraints. Raise capacity issues for scope clarification.
- Keep the evaluation process reproducible using the project's documented setup and commands.

## 10. Approval Status

This is a proposed evaluation plan based on the SOW. The annotation protocol, exact evaluation split, and execution details remain subject to project review and approval. Implementation and model calls with project clinical notes must not begin before the required approval and privacy conditions are satisfied.

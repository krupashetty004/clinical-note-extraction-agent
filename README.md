# AI-Powered Clinical Note Extraction and Coding Agent (MVP)

## Current Status

**Phase:** Planning and research. Architecture and technology choices remain proposals until Mirai Labs gives formal approval.

**Implementation gate:** Do not begin feature implementation or send project clinical notes to a model until the required approval and data-handling checks are complete.

This private repository contains the planning deliverables for the Mirai Labs clinical note extraction agent MVP.

## Project Objective

Propose a local, single-reviewer MVP that extracts diagnoses, medications, procedures, allergies, and vital signs from Mirai Labs-provided English clinical notes, links items to evidence in the original note, retrieves ICD-10 diagnosis candidates, verifies outputs independently, and routes unresolved items for human review.

The system must support structured JSON export and repeatable evaluation against a manually labelled gold standard and a naive single-prompt baseline. It is an assistive review tool, not an autonomous clinical decision-maker.

## Scope Summary

- Local/localhost operation; one reviewer.
- Approximately 5,000 Mirai Labs-provided clinical transcriptions across about 40 specialties, plus the supplied ICD-10 table.
- Original-note evidence spans and character offsets.
- ICD-10 diagnosis candidates only; procedure-code assignment is excluded.
- Independent verification, bounded agent retries, reconciliation, abstention, and escalation.
- Local reviewer interface, privacy-safe trace viewing, and JSON export.
- Free-tier services only; no paid API keys or GPU-dependent infrastructure.

OCR/scanned notes, EHR/billing integration, cloud and multi-user deployment, model fine-tuning, and external clinical-note sourcing are outside the SOW scope.

## Documentation Structure

- `/docs/requirements.md` — SOW requirements, acceptance criteria, constraints, and deliverables
- `/docs/questions-and-assumptions.md` — project questions, assumptions, and confirmed clarifications
- `/docs/market-research.md` — commercial products, open-source tools, papers, and project-relevant findings
- `/docs/solution-proposal.md` — proposed solution and scope
- `/docs/architecture.md` — logical components, data flow, trust boundaries, and architecture diagram
- `/docs/technology-stack.md` — technology candidates, justifications, and pending provider checks
- `/docs/development-timeline.md` — milestones, post-approval schedule, and constraints
- `/docs/evaluation-plan.md` — gold standard, metrics, acceptance thresholds, and challenge tests
- `/docs/research-references.md` — working list of source references

## Confidentiality and Data Handling

- Keep the repository private.
- Do not commit the confidential SOW, clinical datasets, or patient records.
- Use only Mirai Labs-provided clinical notes for the project.
- Mask identifying information locally before any approved external model call.
- Never expose protected information in traces, logs, or demonstration material.

## Approval and Reporting

All architecture, provider, and technology decisions remain proposed until approval. Do not claim that any acceptance target has been met until evaluation results have been measured. Record unfinished tests and constraints explicitly.

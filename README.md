# AI-Powered Clinical Note Extraction and Coding Agent

## Current Status

**Phase:** Revised planning for a hosted, doctor-centred clinical workflow assistant. Documentation is being aligned; implementation status must be confirmed from code/tests, not inferred from the architecture.

**Approval gate:** The hosted doctor workspace expands the original SOW's localhost/single-reviewer/text-only scope. Do not process Mirai Labs clinical notes, patient data, images, or audio in hosted/external services until Mirai Labs has approved the expanded scope and exact data-handling/provider arrangement in writing. Use synthetic data for public demo and deployment tests.

## Project Objective

The original SOW proposes an assistive clinical-note extraction and coding agent that extracts diagnoses, medications, procedures, allergies, and vital signs/key measurements; links items to evidence in the original note; retrieves ICD-10 diagnosis candidates from the supplied table; independently verifies results; and sends uncertain/unsupported items to review.

The revised product proposal adds a hosted doctor's workspace with role-based access, patient/encounter history, a doctor-managed knowledge base, multimodal knowledge ingestion, retrieval-augmented generation (RAG), central model settings, and persistent hosted storage. The system is not an autonomous clinical decision-maker.

## Revised Stack Proposal (All Free Tiers / ₹0 Target)

- **UI:** Django templates + HTMX + Bootstrap (no React)
- **Application:** Django / Python, with server-side permission enforcement
- **Hosted web app:** Render Free; cold starts and ephemeral filesystem are expected constraints
- **Relational database:** Neon Free PostgreSQL
- **Vector search:** pgvector within Neon PostgreSQL
- **File storage:** Neon Object Storage Free, S3-compatible/private; must be smoke-tested
- **Storage contingency:** Supabase Storage Free only if Neon Object Storage fails documented tests
- **Embeddings:** Local sentence-transformers candidate, benchmarked against the free host's CPU/memory
- **OCR:** Tesseract for the initial printed-text scope
- **Audio transcription:** A tested local CPU option or an explicitly approved free-tier API
- **LLM:** Central provider/model adapter with allowlisted models and free-tier usage controls

These are proposed selections; compatibility, current quotas, model policies, and private-storage access must be verified at implementation/deployment time. No paid service/API or silent paid fallback is allowed. Free tiers are limited and do not guarantee unlimited uptime or processing.

## Original SOW Scope Still Applies

- Input: Mirai Labs-provided English clinical text notes and supplied ICD-10 reference table.
- Extract diagnoses, medications, procedures, allergies, vital signs/key measurements.
- Require original-note evidence and character offsets for accepted items.
- Retrieve diagnosis-code candidates only; procedure-code assignment remains out of scope.
- Independent verification, evidence gates, bounded agent loop, reconciliation, abstention, human review and privacy-safe traces.
- At least 100 manually labelled notes across 10+ specialties before prompt tuning; compare against naive single-prompt baseline and report the SOW's acceptance metrics.
- No paid API keys or GPU-dependent infrastructure.

The requested hosted deployment, multi-user roles, patient history, OCR/audio knowledge ingestion and dynamic RAG knowledge base are **scope expansions pending formal approval**; they do not silently replace original SOW acceptance criteria or exclusions.

## Documentation

| File | Purpose |
|---|---|
| `docs/requirements.md` | Original requirements, proposed expanded features, access/privacy requirements and unresolved scope conflicts |
| `docs/questions-and-assumptions.md` | Approval questions, free-tier assumptions, provider decisions and blockers |
| `docs/market-research.md` | Commercial products, open-source tools, research papers and new hosting options |
| `docs/solution-proposal.md` | Doctor-centred workflow, original clinical extraction pipeline, editable knowledge base and RAG proposal |
| `docs/architecture.md` | End-to-end architecture and Mermaid diagram including technologies and data stores |
| `docs/technology-stack.md` | Justification for Django, Render, Neon PostgreSQL/pgvector, Object Storage and AI options |
| `docs/development-timeline.md` | Revised milestone plan and expanded-scope risks |
| `docs/evaluation-plan.md` | Original SOW metrics plus tests for permissions, patient isolation, uploads, RAG, settings and deployment |
| `docs/hosted-deployment-plan.md` | Free-tier Render/Neon deployment, private object storage, environment configuration and smoke tests |
| `docs/research-references.md` | Primary research, official tool and current hosting/quota references |

## Confidentiality and Safe Demo

- Keep this repository private.
- Never commit the SOW, source clinical datasets, real patient records, API keys, or uploaded files.
- The public hosted demo uses synthetic patient data unless written approval says otherwise.
- Keep uploaded files in private object storage; never rely on Render's ephemeral local filesystem for persistent content.
- Keep original clinical-note evidence separate from RAG reference context and historical patient records.
- Check access control for every patient, encounter, note, knowledge file, export and configuration endpoint.
- Mask likely identifiers locally before approved external calls, and preserve the mapping from transformed text to original offsets.
- Keep protected information and credentials out of logs/traces.
- If any free quota is exhausted, show an error/defer work; never trigger a paid upgrade or silently switch providers.

## Implementation and Reporting Rules

All new scope and provider decisions require approval. Do not call a component implemented until source code and tests support the claim. Do not claim an evaluation target was achieved until measured; report each as **Pass**, **Fail**, or **Not yet measured**. The six-day post-approval window is high-risk for the expanded scope; required gold-standard and challenge-set sizes must not be silently reduced.

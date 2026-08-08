# AI Credit Analysis V4 — Document-First Credit Underwriting

AI Credit Analysis V4 is a document-first corporate credit underwriting and decision-support prototype.

## Core workflow

**Upload Documents → Classify → Extract → Validate → Financial Spreading → Credit Analysis → Risk Review → Credit Memorandum**

The platform is designed to reduce manual re-keying and preserve an audit trail from each extracted field back to its source document/location.

## V4 capabilities

- Multi-file upload for financial and credit documents.
- Parsing of XLSX/XLSM, text-based PDF, DOCX, CSV, and TXT.
- Automatic document classification.
- Extraction of core borrower, financial, facility, and collateral fields.
- Confidence score and source trace for extracted values.
- Human validation/edit step before underwriting.
- Financial ratios and cash-flow-first debt-service assessment.
- Working-capital cycle and external funding need.
- Facility sizing based on the tightest constraint: cash flow, leverage, working capital, and collateral.
- Collateral haircut and legal-enforceability controls.
- Stress testing.
- Indicative IFRS 9 staging / PD-LGD-EAD-ECL support fields (not calibrated regulatory estimates).
- Draft credit memorandum for committee review.
- Health and capabilities endpoints.

## Privacy and confidentiality

The public application, README, source comments, and user interface contain no customer names or case-specific confidential information.

The prototype processes uploaded files inside the web request and does not intentionally persist them in a database. Production use requires bank-approved controls for encryption, retention, access control, audit logs, data residency, secrets management, backups, and incident response.

## Important limitation

Scanned/image-only PDFs require an OCR/document-AI layer in production. V4 currently extracts text from machine-readable PDFs and structured Office files.

## Risk-governance principles

The design follows a repayment-capacity-first approach: collateral is a risk mitigant, not a substitute for a sound assessment of the borrower. It also separates automated extraction/scoring from human approval authority.

Reference frameworks:
- Basel Committee on Banking Supervision, *Principles for the Management of Credit Risk* (30 April 2025): https://www.bis.org/bcbs/publ/d595.htm
- Basel Framework, credit risk mitigation / legal enforceability: https://www.bis.org/basel_framework/chapter/CRE/22.htm
- IFRS 9 Financial Instruments: https://www.ifrs.org/issued-standards/list-of-standards/ifrs-9-financial-instruments/

## Run locally

```bash
pip install -r requirements.txt
uvicorn app:app --reload
```

Open http://127.0.0.1:8000

## Railway

The included `Dockerfile` listens on `$PORT`, so it can be deployed using the existing Railway service.

## Production roadmap

1. OCR/document AI for scanned Arabic/English files.
2. Multi-year financial statement spreading with reconciliation checks.
3. Bank-statement transaction analytics and cash-flow reconstruction.
4. Borrower/group exposure and concentration analysis.
5. Policy/rule engine by product, sector, grade, and delegated authority.
6. Role-based approval workflow, maker-checker controls, and immutable audit log.
7. Calibrated PD/LGD/EAD/ECL models with model governance and validation.
8. Exportable PDF/DOCX credit memorandum and committee pack.
9. Database layer with encryption, tenancy, retention, and access policies.
10. Integration APIs for core banking, credit bureau, KYC/AML, collateral, and document repositories.

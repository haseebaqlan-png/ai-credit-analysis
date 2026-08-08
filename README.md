# AI Credit Analysis V5 — AI-Powered Corporate Underwriting

V5 turns the project into an AI-assisted, document-first corporate credit underwriting prototype.

## Capabilities
- OpenAI Responses API integration.
- Direct PDF/image understanding plus local normalization for Excel, Word, CSV and text.
- Multi-year financial spreading and visual trend charts.
- Evidence/confidence audit trail.
- Ratios, working capital, cash-flow/DSCR, facility sizing and collateral analysis.
- 5Cs, management/governance, stress testing, IFRS 9 indicators.
- AI-generated Arabic committee memorandum.
- Risks, mitigants, conditions, covenants, early warnings and committee questions.
- Human review remains mandatory.

## Railway variables
Add in Railway → Service → Variables:
- `OPENAI_API_KEY` = secret API key. Never commit it to GitHub.
- `OPENAI_MODEL` = `gpt-5` (optional default)
- `MAX_FILE_MB` = `15`
- `MAX_TOTAL_MB` = `40`

## Production warning
Before live customer data is uploaded, the institution must approve provider use, privacy/data classification, retention/deletion, data residency, encryption, RBAC/MFA, audit logging, DLP, vendor risk, model governance and validation.

The application uses `store=False` for Responses API calls. This does not replace an institutional privacy review.

## Run
```bash
pip install -r requirements.txt
export OPENAI_API_KEY="..."
uvicorn main:app --reload
```

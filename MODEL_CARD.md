# Model Card — Credit Underwriting V3

## Intended use
Corporate / SME credit decision support and analyst workflow acceleration.

## Not intended for
- Fully automated credit approval or decline without human review.
- Regulatory capital calculation.
- Production IFRS 9 impairment without bank-specific calibration and governance.
- Consumer lending or protected-class decisioning.

## Decision architecture
1. Financial score.
2. Qualitative/business score.
3. Data-quality overlay.
4. Independent policy gates.
5. Capacity-based facility sizing.
6. Scenario stress tests.
7. Indicative IFRS 9 staging and ECL components.

## Key model-risk controls to add before production
- Historical calibration and discrimination testing (AUC/Gini/KS as appropriate).
- Calibration testing of PD bands.
- LGD workout/recovery database and collateral realization timing.
- EAD/CCF calibration for revolving and off-balance-sheet products.
- Override policy and reason codes.
- Versioned thresholds and sector-specific scorecards.
- Back-testing, stability monitoring, drift detection, and annual validation.
- Access control, audit logging, maker-checker workflow, and committee approvals.

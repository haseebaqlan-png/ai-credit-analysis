# SECURITY & DATA HANDLING

V4 is a prototype and must not be treated as a production banking system without security hardening.

Required production controls include:
- TLS in transit and encryption at rest.
- Strong authentication, MFA, RBAC, and least privilege.
- Tenant/client isolation.
- Immutable audit logs for uploads, extractions, overrides, approvals, and exports.
- Configurable retention and secure deletion.
- Secrets management outside source code.
- Malware scanning and file-size/type validation.
- DLP controls and restricted exports.
- Data residency and cross-border transfer controls.
- Backup/recovery, monitoring, incident response, and vulnerability management.
- Model governance, change control, validation, and versioning.

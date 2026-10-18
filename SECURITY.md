# Security Policy

## Reporting

Please report suspected vulnerabilities, leaked secrets, or content you believe
was copied from a third party through GitHub's private vulnerability reporting
("Security" tab, "Report a vulnerability") on this repository. Do not open a
public issue for these. Expect an acknowledgement within a week.

## Scope and posture

- The service listens on `127.0.0.1` by default and has no authentication or
  TLS. Exposing it on other interfaces is the operator's responsibility.
- It serves only `GET /metrics` and `GET /healthz`; it accepts no input that
  changes state.
- Log output is redacted for common credential patterns. Redaction is
  best-effort; do not log secrets deliberately.
- Metric label values are sanitized and cardinality-capped to limit resource use.
- The project ships only synthetic data and needs no credentials. Any real
  client you write should take secrets from the environment, never from source.

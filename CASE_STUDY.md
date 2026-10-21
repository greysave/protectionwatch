# Case study: fleet health and RPO observability

> Fictional scenario using the seeded built-in client. No production monitoring data is included.

## Scenario

**Example Industries** wants an operator view and Prometheus metrics for a fictional protection fleet. Stale targets must not keep reporting old health as if it were current, and metric labels must stay bounded.

## Approach

- Poll an abstract fleet client on a fixed interval.
- Back off after failures and withhold stale target data.
- Cap targets and label values to control Prometheus cardinality.
- Expose health, RPO breaches, job counts and duration histograms.
- Redact secrets from every log path, including tracebacks.

## Reproduce

```console
protectionwatch dashboard --once
protectionwatch once --targets 5
```

## Verified synthetic result

```text
protectionwatch  targets=12 fresh=12 stale=0 polls ok=1 failed=0

TARGET               GROUP      HEALTH         RPO  OBJECTIVE     AGE
node-001             alpha      critical     2h30m      1h00m      0s
node-002             bravo      critical     5h00m      2h00m      0s
node-005             alpha      healthy      1h48m      2h00m      0s
node-006             bravo      warning      4h12m      3h00m      0s
node-012             delta      healthy      1h30m      3h00m      0s
```

The same run emitted Prometheus series such as:

```text
protectionwatch_target_health{target="node-001",group="alpha",state="critical"} 1
```

## What this demonstrates

Observability design, Prometheus exposition, RPO reasoning, stale-data safety, bounded cardinality, threaded shutdown and operator-focused terminal UX.

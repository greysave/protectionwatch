# protectionwatch

Unofficial, vendor-neutral monitoring service for a **synthetic** data-protection
fleet. It polls an abstract client, keeps a bounded in-memory view, and exposes
health, RPO and job metrics in Prometheus text format, with an optional terminal
dashboard. Standard library only at runtime.

> Not affiliated with Cohesity or any other vendor. The API contract is invented
> for this project and all data is generated from a seeded random source. See
> [NOTICE](NOTICE) and [PROVENANCE.md](PROVENANCE.md).

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'

protectionwatch once --targets 5          # print metrics once
protectionwatch dashboard --once          # print one dashboard frame
protectionwatch serve --port 9877         # http://127.0.0.1:9877/metrics
protectionwatch dashboard                 # live dashboard, Ctrl-C to quit
```

`serve` binds to `127.0.0.1` by default and has no authentication; put a reverse
proxy in front of it if you change `--host`.

## Design

| Concern | Behaviour |
|---|---|
| Client | `FleetClient` protocol (`fetch_fleet()`); `SyntheticClient` is the only implementation shipped. |
| Polling | Fixed interval; exponential backoff (capped) while polls fail; stops promptly on shutdown. |
| Stale data | A target not refreshed within `--stale-after` is flagged `protectionwatch_target_stale=1`; its health, RPO and job values are **withheld**, not replayed. Targets unseen for the retention window are evicted. |
| Cardinality | `target` is sanitized, de-duplicated and capped (`--max-targets`, extras counted in `protectionwatch_dropped_targets_total{reason="cap"|"duplicate"}`, a cumulative counter that increments once per poll in which a target is dropped). `group` and `job_class` labels admit a fixed number of values, the rest fold into `other`. Job states and health states are closed enums. |
| Logging | All log output passes a redaction filter (Bearer/Basic/Authorization headers, Cookie headers, quoted and unquoted `password=`/`token=`/`api_key=` values including values with spaces, URL userinfo), including tracebacks. |
| Shutdown | SIGINT/SIGTERM stop the poller, the HTTP server and join both threads. |

### Metrics

`protectionwatch_target_stale`, `_target_data_age_seconds`, `_target_health`,
`_target_rpo_seconds`, `_target_rpo_objective_seconds`, `_target_rpo_breached`,
`_jobs`, `_job_duration_seconds` (histogram), `_polls_total`,
`_last_successful_poll_timestamp_seconds`, `_last_poll_duration_seconds`,
`_consecutive_poll_failures`, `_dropped_targets_total`, `_label_overflow_total`,
`_build_info`.

Every per-target metric carries the same `target` and `group` labels.

Endpoints: `/metrics`, `/healthz` (200 only when at least one target is fresh). Query strings
(e.g. `/metrics?foo=bar`) are ignored.

## Related projects

`protectionwatch` is one of five independent, synthetic-data projects that together sketch a small
data-protection toolkit: simulate a platform, collect from it, monitor it, analyse history and
check policy. They are **separate packages with separate, invented contracts**; none imports
another and none depends on another at install time.

| Project | Role |
|---|---|
| [protectionsim](https://github.com/greysave/protectionsim) | Deterministic local HTTP simulator of a synthetic data-protection API. |
| [backup-fleet-async](https://github.com/greysave/backup-fleet-async) | Asyncio collector that polls job status from many clusters into JSONL. |
| [rpo-analytics](https://github.com/greysave/rpo-analytics) | SQLite-backed RPO compliance, drift and capacity analytics over run history. |
| [protection-policy-check](https://github.com/greysave/protection-policy-check) | Policy-as-code evaluator for job inventories, with a CI exit code. |

Today it polls only its own `SyntheticClient`; a client for `protectionsim` or another source would implement the `FleetClient` protocol. Metrics are standard Prometheus text, so any scraper can read them.

## Portfolio case study

See [the verified synthetic case study](CASE_STUDY.md) for a fictional operational scenario, reproducible commands and captured results.

## Development

```bash
pytest
ruff format --check . && ruff check .
mypy
```

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

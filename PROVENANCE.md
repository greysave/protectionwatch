# Provenance

This repository was written from scratch as a clean-room project.

- **Origin:** a new repository with a single initial commit. No git history,
  source files, schemas, SDK code, endpoints, hostnames, credentials, fixtures
  or documentation were copied or adapted from any employer, client or vendor
  project, quarantined or otherwise.
- **API contract:** the `FleetClient` / `TargetSnapshot` / `JobResult` model in
  `src/protectionwatch/model.py` is invented and generic. It deliberately does
  not mirror any vendor's resource names, field names or wire format.
- **Data:** every value comes from `SyntheticClient`, a seeded pseudo-random
  generator. Target names (`node-001`), groups (`alpha`...) and job classes
  (`snapshot`, `replication`...) are generic placeholders.
- **Dependencies:** none at runtime. Development tools (pytest, ruff, mypy) are
  pinned in `pyproject.toml` and are used as installed from PyPI.
- **Author attribution:** Greysave contributors.
- **Verification:** the tree was scanned for vendor, employer and customer
  identifiers, URLs, hostnames and credential patterns before the first commit;
  CI additionally runs gitleaks on every push and pull request.

If you believe any content here originates from a third party, please report it
as described in [SECURITY.md](SECURITY.md).

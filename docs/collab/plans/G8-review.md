# G8 hardening and handoff review list

- Write the threat model for ownership, sessions, SSE replay, report and scheduled outputs, source excerpts, exports and developer tooling. Resolve Q-017 before deployment.
- Implement per-owner usage and cost metering and budgets. Use the G7 duration and retry logs to design aggregation without storing prompts, headers or source excerpts.
- Load test API, worker and PostgreSQL at representative fixture volume. Measure queue depth, scheduler fairness, lag, connection use and gateway cost. Exercise recovery and backfill under concurrency.
- Validate publication after real marker changes, delayed availability, corrections and supported fiscal labels. Confirm Q-018 currency rules before changing the unconfirmed labels.
- Implement report and chat retention and purge. Exercise deletion of expired previews, turn events and derived outputs without removing active saved artifacts.
- Produce the deployment image and Compose option plus configuration, migrations, rollback procedures and an operator runbook. Verify owner scope and read-only source separation in the package.
- Run the README on a fresh environment and add `HANDOFF.md`. Include reviewed Functions Assist styling if Q-027 has been answered, browser checks, deployment results and sanitized model outcomes.

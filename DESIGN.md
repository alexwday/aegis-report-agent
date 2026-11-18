# Design

A report is an immutable versioned specification. A saved version pins its section pipelines, defaults and formatting. A draft can be previewed in isolation, compared with an authorized baseline and explicitly saved into a new version. Scheduled runs pin the saved version and capture the resolved fiscal periods, source revisions, outputs and per-block evidence.

The API authenticates callers through one identity interface. The API and workers access report state through a dedicated `rpt` writer and read source tables through typed adapters with separate read-only credentials. Jobs and streamed chat events are persisted to support retries and reconnects. Adapters apply source-specific bank, period, document and evidence rules behind a common interface.

The [G0 plan](docs/collab/plans/PLAN.md) contains the component and data diagrams, stage model, API and UI proposals, publication rules and gates. Its [draft SQL](docs/collab/plans/rpt-draft.sql) is a design artifact. The [decision log](docs/collab/DECISIONS.md) records the options and reasons.

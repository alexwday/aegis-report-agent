# API examples from the local fixture

Regenerate with `uv run --no-sync python scripts/capture_api_examples.py` while
`SCHEDULE_POLL_SECONDS=0.25 ./scripts/dev` is running. Responses are selected fields from the live synthetic API.
Resource IDs are normalized consistently. Values and state transitions come from the fixture.

### GET `/v1/templates`

HTTP 200 response

```json
[
  {
    "id": "quarterly-earnings",
    "title": "Quarterly earnings",
    "kind": "system"
  }
]
```

### POST `/v1/drafts`

```json
{
  "template": "quarterly-earnings",
  "bank": "SYN1"
}
```

HTTP 201 response

```json
{
  "id": "00000000-0000-4000-8000-000000000001",
  "revision": 1,
  "report_id": null
}
```

### POST `/v1/drafts/00000000-0000-4000-8000-000000000001/save`

```json
{
  "revision": 1
}
```

HTTP 201 response

```json
{
  "report_id": "00000000-0000-4000-8000-000000000002",
  "version": 1,
  "draft_revision": 2
}
```

### POST `/v1/reports/00000000-0000-4000-8000-000000000002/runs`

```json
{
  "version": 1,
  "period": {
    "year": 2090,
    "quarter": 2
  },
  "request_key": "00000000-0000-4000-8000-000000000003"
}
```

HTTP 202 response

```json
{
  "id": "00000000-0000-4000-8000-000000000004"
}
```

### GET `/v1/runs/00000000-0000-4000-8000-000000000004`

HTTP 200 response

```json
{
  "id": "00000000-0000-4000-8000-000000000004",
  "state": "succeeded",
  "mode": "generate",
  "period": {
    "year": 2090,
    "quarter": 2
  }
}
```

### GET `/v1/runs/00000000-0000-4000-8000-000000000004/evidence/6a389eb3041fd8c02ab9b07007394841bb40604a1b664c2f10452ae13fca4adf/detail`

HTTP 200 response

```json
{
  "source": "benchmarking",
  "locator": "Derived dataset · snapshot 2090-10-01 00:00:00 · SYN1-CA · Net Income · Enterprise · FY2090 Q2",
  "excerpt": "Net Income 435 millions CAD"
}
```

### POST `/v1/conversations`

```json
{
  "draft_id": "00000000-0000-4000-8000-000000000001",
  "period": {
    "year": 2090,
    "quarter": 2
  }
}
```

HTTP 201 response

```json
{
  "draft_id": "00000000-0000-4000-8000-000000000001",
  "period": {
    "year": 2090,
    "quarter": 2
  },
  "id": "00000000-0000-4000-8000-000000000005"
}
```

### POST `/v1/conversations/00000000-0000-4000-8000-000000000005/turns`

```json
{
  "message": "Make Net income staged.",
  "request_key": "stage-first"
}
```

HTTP 202 response

```json
{
  "id": "00000000-0000-4000-8000-000000000006",
  "state": "queued",
  "last_sequence": 1
}
```

### GET `/v1/conversations/00000000-0000-4000-8000-000000000005/turns/00000000-0000-4000-8000-000000000006/events`

The request used `Last-Event-ID: 1`. The first resumed frames follow.

```text
: heartbeat

id: 2
event: started
data: {}

id: 3
event: tool
data: {"name":"propose_patch"}
```

### GET `/v1/conversations/00000000-0000-4000-8000-000000000005/turns/00000000-0000-4000-8000-000000000006`

HTTP 200 response

```json
{
  "state": "succeeded",
  "proposal": {
    "revision": 2,
    "operations": [
      {
        "section_id": "net-income",
        "op": "set_mode",
        "mode": "staged"
      }
    ]
  },
  "last_sequence": 6
}
```

### POST `/v1/conversations/00000000-0000-4000-8000-000000000005/turns/00000000-0000-4000-8000-000000000006/accept`

```json
{
  "revision": 2
}
```

HTTP 200 response

```json
{
  "draft_id": "00000000-0000-4000-8000-000000000001",
  "revision": 3
}
```

### POST `/v1/drafts/00000000-0000-4000-8000-000000000001/save`

```json
{
  "revision": 2
}
```

HTTP 409 response

```json
{
  "detail": "stale_draft_revision"
}
```

### POST `/v1/drafts/00000000-0000-4000-8000-000000000001/previews`

```json
{
  "revision": 3,
  "period": {
    "year": 2090,
    "quarter": 2
  },
  "section_id": "net-income",
  "stop_after": "gather"
}
```

HTTP 202 response

```json
{
  "id": "00000000-0000-4000-8000-000000000007"
}
```

### GET `/v1/runs/00000000-0000-4000-8000-000000000007/output.json`

HTTP 200 response

```json
{
  "completion": "gathered",
  "section": {
    "id": "net-income",
    "mode": "staged",
    "resolved_periods": [
      {
        "year": 2090,
        "quarter": 2
      }
    ]
  },
  "stage_kinds": [
    "retrieve"
  ],
  "source": {
    "evidence_state": "matched",
    "message": "This source returned evidence."
  }
}
```

### POST `/v1/drafts/00000000-0000-4000-8000-000000000001/previews`

```json
{
  "revision": 3,
  "period": {
    "year": 2090,
    "quarter": 2
  },
  "baseline_run_id": "00000000-0000-4000-8000-000000000004"
}
```

HTTP 202 response

```json
{
  "id": "00000000-0000-4000-8000-000000000008"
}
```

### GET `/v1/runs/00000000-0000-4000-8000-000000000008/output.json`

HTTP 200 response

```json
{
  "diff": {
    "added": [],
    "removed": [],
    "changed": [
      "net-income"
    ]
  },
  "baseline_run_id": "00000000-0000-4000-8000-000000000004"
}
```

### POST `/v1/drafts/00000000-0000-4000-8000-000000000001/save`

```json
{
  "revision": 3
}
```

HTTP 201 response

```json
{
  "report_id": "00000000-0000-4000-8000-000000000002",
  "version": 2,
  "draft_revision": 4
}
```

### PUT `/v1/reports/00000000-0000-4000-8000-000000000002/schedule`

```json
{
  "version": 2,
  "enabled": true,
  "period": {
    "year": 2090,
    "quarter": 2
  },
  "quiet_seconds": 2
}
```

HTTP 200 response

```json
{
  "report_id": "00000000-0000-4000-8000-000000000002",
  "version": 2,
  "period": {
    "year": 2090,
    "quarter": 2
  },
  "next_period": {
    "year": 2090,
    "quarter": 2
  },
  "enabled": true,
  "revision": 1,
  "timezone": "America/Toronto",
  "quiet_seconds": 2.0,
  "correction_days": 14,
  "provisional_after_hours": null
}
```

### POST `/v1/reports/00000000-0000-4000-8000-000000000002/schedule/enqueue`

HTTP 202 response

```json
{
  "id": "00000000-0000-4000-8000-000000000009"
}
```

### GET `/v1/reports/00000000-0000-4000-8000-000000000002/schedule/runs?limit=1`

HTTP 200 response

```json
[
  {
    "id": "00000000-0000-4000-8000-000000000009",
    "version": 2,
    "period": {
      "year": 2090,
      "quarter": 2
    },
    "state": "waiting",
    "error_code": null
  }
]
```

### GET `/v1/reports/00000000-0000-4000-8000-000000000002/schedule/periods?limit=3`

HTTP 200 response

```json
[
  {
    "period": {
      "year": 2090,
      "quarter": 2
    },
    "state": "published",
    "generation": 1,
    "current_kind": "complete",
    "output_url": "/v1/runs/00000000-0000-4000-8000-000000000009/output.json"
  }
]
```

A pending check returns a normal run ID. The poller adopts it when inputs are stable.

### GET `/v1/runs/00000000-0000-4000-8000-000000000004/output.pdf`

The saved run returned `HTTP 200`, `application/pdf` and a valid PDF signature.

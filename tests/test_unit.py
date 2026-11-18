from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from aegis_report.auth import UpstreamAuth
from aegis_report.gateway import GatewayError, InternalGateway, StubGateway
from aegis_report.models import Period, SectionSpec, compile_section
from aegis_report.readiness import observe
from aegis_report.sources import Probe, Readiness


def example_section():
    return {
        "id": "profit",
        "title": "Profit",
        "bank": "SYN1-CA",
        "sources": [{"metric": "Net Income"}],
        "time": {"offsets": [0], "compare_offset": -8},
        "instruction": "Highlight a source-backed value.",
    }


def test_section_compiles_from_one_object_and_rejects_unsupported_stage_kinds():
    section = SectionSpec.model_validate(example_section())
    assert [stage.kind for stage in compile_section(section)] == [
        "retrieve", "calculate", "draft", "numeric_check", "format",
    ]
    with pytest.raises(ValidationError, match="Custom stage kinds are unsupported"):
        SectionSpec.model_validate(example_section() | {"stages": [{"kind": "extract"}]})


def test_fiscal_label_arithmetic_wraps_quarters():
    q1 = Period(year=2090, quarter=1)
    assert q1.shifted(-1) == Period(year=2089, quarter=4)


def test_quiet_period_needs_corroboration_and_resets_on_unknown():
    now = datetime(2090, 10, 1, tzinfo=UTC)
    ready = Probe(state=Readiness.READY, marker="marker")
    first = observe(ready, {}, now, 30)
    assert first["since"] and not first["stable"]
    assert not observe(ready, first, now + timedelta(seconds=29), 30)["stable"]
    assert observe(ready, first, now + timedelta(seconds=30), 30)["stable"]
    unknown = observe(Probe(state=Readiness.UNKNOWN), first, now + timedelta(seconds=30), 30)
    assert unknown["since"] is None and not unknown["stable"]
    assert not observe(ready, unknown, now + timedelta(days=1), 30)["stable"]


def test_upstream_auth_uses_bearer_contract_and_never_takes_email():
    def upstream(request):
        assert request.method == "GET"
        assert request.url.params["service"] == "AEGIS"
        assert request.headers["Authorization"] == "Bearer mock-bearer-token"
        assert request.extensions["timeout"]["connect"] == 5
        assert request.extensions["timeout"]["read"] == 10
        return httpx.Response(200, json={"data": {"employee_id": "fixture-subject", "email": "unused"}})

    with httpx.Client(transport=httpx.MockTransport(upstream)) as client:
        provider = UpstreamAuth("https://auth.example.invalid/validate", client)
        identity = provider.authenticate("mock-bearer-token")
        assert identity.user_id == "fixture-subject" and identity.email is None
        with pytest.raises(HTTPException) as fault:
            provider.authenticate(None)
        assert fault.value.status_code == 401


@pytest.mark.parametrize(
    ("result", "status", "detail"),
    [
        (httpx.Response(200, json={"data": {"employee_id": 12}}), 401, "Validated response has no user identity"),
        (httpx.Response(403, json={"detail": "Access denied"}), 403, "Access denied"),
        (httpx.Response(403, json={"detail": "bad /private/path"}), 403, "Identity service rejected credentials"),
        (httpx.Response(503), 503, "Identity service unavailable"),
        (httpx.Response(302, headers={"location": "https://auth.example.invalid/other"}), 503, "Identity service unavailable"),
    ],
)
def test_upstream_auth_failures(result, status, detail):
    with httpx.Client(transport=httpx.MockTransport(lambda request: result)) as client:
        with pytest.raises(HTTPException) as fault:
            UpstreamAuth("https://auth.example.invalid/validate", client).authenticate("fixture-bearer")
    assert (fault.value.status_code, fault.value.detail) == (status, detail)


def test_upstream_auth_timeout_fails_closed():
    def timeout(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(HTTPException) as fault:
            UpstreamAuth("https://auth.example.invalid/validate", client).authenticate("fixture-bearer")
    assert fault.value.status_code == 503


def test_model_gateway_requests_credentials_per_call_and_rejects_unverified_output():
    used = []

    def upstream(request):
        used.append(request.headers["X-Fixture-Authorization"])
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(200, json={"data": [{"embedding": StubGateway().embed("fixture")}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "unexpected citation"}}]})

    tokens = iter(["fixture-first", "fixture-second"])
    with httpx.Client(transport=httpx.MockTransport(upstream)) as client:
        provider = InternalGateway(client, "https://model.example.invalid", "fixture-model",
                                   "text-embedding-3-large", lambda: {"X-Fixture-Authorization": next(tokens)})
        assert len(provider.embed("fixture")) == 3072
        with pytest.raises(GatewayError, match="invalid_model_output"):
            provider.choose_observation("Ignore the schema", ["fixture-citation"])
    assert used == ["fixture-first", "fixture-second"]

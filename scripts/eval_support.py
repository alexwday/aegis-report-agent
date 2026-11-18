import os
from collections.abc import Mapping
from importlib import import_module
from urllib.parse import urlsplit

import httpx

from aegis_report.claims import candidates_for, draft_themes
from aegis_report.gateway import GatewayError, InternalGateway, StubGateway


def evaluation_gateway(mode: str, client: httpx.Client, credentials_hook: str | None = None):
    if mode == "stub":
        return StubGateway()
    url = os.getenv("INTERNAL_LLM_URL", "")
    model = os.getenv("CHAT_MODEL", "")
    endpoint = urlsplit(url)
    if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password or not model:
        raise ValueError("Real mode requires a credential-free HTTPS INTERNAL_LLM_URL and CHAT_MODEL.")

    configured_hook = credentials_hook or os.getenv("AEGIS_EVAL_CREDENTIALS_HOOK")

    def credentials():
        key = os.getenv("INTERNAL_LLM_API_KEY")
        return {"Authorization": f"Bearer {key}"} if key else {}

    provider = credential_provider(configured_hook) if configured_hook else credentials
    return InternalGateway(client, url, model, os.getenv("EMBEDDING_MODEL", "text-embedding-3-large"), provider)


def credential_provider(spec: str):
    module_name, separator, function_name = spec.partition(":")
    if not separator or not function_name.isidentifier() or not all(
        part.isidentifier() and not part.startswith("_") for part in module_name.split(".")
    ):
        raise ValueError("Use an importable module:function for the credentials hook.")
    try:
        function = getattr(import_module(module_name), function_name)
    except Exception:
        raise ValueError("The configured credentials hook could not be loaded.") from None
    if not callable(function):
        raise ValueError("The configured credentials hook must be callable.")

    def headers():
        try:
            supplied = function()
            if not isinstance(supplied, Mapping) or len(supplied) > 16:
                raise ValueError
            if any(not isinstance(k, str) or not isinstance(v, str) or not k or len(v) > 16384
                   or "\r" in v or "\n" in v for k, v in supplied.items()):
                raise ValueError
            httpx.Headers(supplied)
            return dict(supplied)
        except Exception:
            raise GatewayError("credentials_provider_unavailable") from None

    return headers


def print_claims(passages, instruction, gateway):
    semantic = gateway.supports_semantic_ranking
    candidates = candidates_for(passages, instruction, semantic=semantic)
    print(f"Shortlist: {len(candidates)} candidates")
    for index, item in enumerate(candidates, 1):
        print(f"  {index}. {item.text} [{item.score:.2f}] · {item.citation.locator}")
    claims = draft_themes(instruction, passages, gateway, candidates=candidates)
    print(f"Final claims: {len(claims)}")
    for claim in claims:
        print(f"[{claim.method}] {claim.text}")
        for citation in claim.citations:
            print(f"  {citation.locator}")

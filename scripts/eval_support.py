import os
from urllib.parse import urlsplit

import httpx

from aegis_report.claims import candidates_for, draft_themes
from aegis_report.gateway import InternalGateway, StubGateway


def evaluation_gateway(mode: str, client: httpx.Client):
    if mode == "stub":
        return StubGateway()
    url = os.getenv("INTERNAL_LLM_URL", "")
    model = os.getenv("CHAT_MODEL", "")
    endpoint = urlsplit(url)
    if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password or not model:
        raise ValueError("Real mode requires a credential-free HTTPS INTERNAL_LLM_URL and CHAT_MODEL.")

    def credentials():
        key = os.getenv("INTERNAL_LLM_API_KEY")
        return {"Authorization": f"Bearer {key}"} if key else {}

    return InternalGateway(client, url, model, os.getenv("EMBEDDING_MODEL", "text-embedding-3-large"), credentials)


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

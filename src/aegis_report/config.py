import json
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    report_dsn: str = field(repr=False)
    source_dsn: str = field(repr=False)
    owner_secret: bytes = field(repr=False)
    local: bool = False
    local_user_id: str = "local-dev-user"
    auth_url: str | None = None
    llm_url: str | None = None
    llm_api_key: str | None = field(default=None, repr=False)
    chat_model: str | None = None
    embedding_model: str = "text-embedding-3-large"
    quiet_seconds: float = 1800
    poll_seconds: float = 1
    retention_days: int = 7
    currencies: dict[str, str] = field(default_factory=lambda: {"CA": "CAD", "US": "USD"})

    @classmethod
    def from_env(cls) -> "Settings":
        local = os.environ.get("ENVIRONMENT") == "local"
        auth_provider = os.environ.get("AUTH_PROVIDER", "local" if local else "")
        auth_url = os.environ.get("AUTH_VALIDATION_URL")
        if auth_provider != ("local" if local else "upstream") or (not local and not auth_url):
            raise ValueError("Set explicit local mode or configure upstream authentication")

        secret = os.environ["OWNER_KEY_SECRET"].encode()
        if len(secret) < 32:
            raise ValueError("OWNER_KEY_SECRET must contain at least 32 bytes")
        source_dsn = os.environ["SOURCE_DATABASE_URL"]
        report_dsn = os.environ["RPT_DATABASE_URL"]
        if source_dsn == report_dsn:
            raise ValueError("Use separate source and report credentials")

        quiet = float(os.environ.get("QUIET_SECONDS", "1800"))
        poll = float(os.environ.get("WORKER_POLL_SECONDS", "1"))
        retention = int(os.environ.get("PREVIEW_RETENTION_DAYS", "7"))
        if not 0 <= quiet <= 86400 or not 0 < poll <= 60 or not 1 <= retention <= 365:
            raise ValueError("Invalid worker timing or retention")
        llm_url = os.environ.get("INTERNAL_LLM_URL")
        model = os.environ.get("CHAT_MODEL")
        if not local and not (llm_url and model):
            raise ValueError("Production requires a configured internal model gateway and chat model")
        for endpoint in (auth_url, llm_url):
            if endpoint:
                parsed = urlsplit(endpoint)
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError("Gateway URLs must be HTTPS and must omit credentials")

        currencies = json.loads(os.environ.get("CURRENCY_MAP", '{"CA":"CAD","US":"USD"}'))
        if not isinstance(currencies, dict) or any(
            not isinstance(code, str) or len(code) != 3 or not code.isalpha() or not code.isupper()
            for code in currencies.values()
        ):
            raise ValueError("CURRENCY_MAP must map symbols or country tags to currency codes")
        local_user = os.environ.get("LOCAL_AUTH_USER_ID", "local-dev-user").strip()
        if local and not local_user:
            raise ValueError("LOCAL_AUTH_USER_ID is empty")
        return cls(
            report_dsn, source_dsn, secret, local, local_user, auth_url,
            llm_url, os.environ.get("INTERNAL_LLM_API_KEY"), model,
            os.environ.get("EMBEDDING_MODEL", "text-embedding-3-large"),
            quiet, poll, retention, currencies,
        )

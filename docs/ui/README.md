# Aegis reference workspace

The reference app demonstrates the quarterly reporting workflow for a finance analyst in Functions Assist. It uses the local FastAPI application and runs with a fabricated source catalog and deterministic assistant. The Functions Assist team owns hosting and embedding. The neutral theme is replaceable when approved styling arrives. [Brand question Q-027](../collab/QUESTIONS.md)

- [Run the demo and walk five tasks](demo.md)
- [Screens and annotated desktop and tablet captures](screens.md)
- [Tokens, typography, components, interaction and accessibility](system.md)
- [API mapping, wording and handoff boundary](integration.md)

The app starts at `/`. Developer tools at `/console` expose raw API requests, the local identity selector and lower-level diagnostics. All normal workflows use the browser's current local identity. The frontend uses browser-native modules, CSS and Canvas and makes same-origin requests. [Reference source](../../ui/reference), [API contract](../../api/openapi.json)

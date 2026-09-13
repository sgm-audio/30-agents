# Security Policy

## API Authentication

- `API_SECRET` is **optional** for local binding (`127.0.0.1`). **Required** when binding to `0.0.0.0` (public).
- Authentication via `X-API-Key` header **or** `?token=` query param. WebSocket `4401` error on failure.

## CORS

- **\*** default in development. Set `CORS_ORIGINS` environment variable in production to restrict origins.

## Environment

- `.env` **must be gitignored**. Never commit `NVIDIA_API_KEY`, `RESEND_API_KEY`, or `HUNTER_API_KEY`.
- If any API key is leaked, rotate it immediately.

## SSRF & Path Guarding

- All outbound HTTP requests must pass `validate_public_http_url` guard.
- File path access resolved through `resolve_allowed_path` — only roots defined in `AGENT_ALLOWED_PATHS` are accessible.

## Vulnerability Reporting

Report security vulnerabilities via [GitHub Security Advisories](https://github.com/30-agents/30-agents/security/advisories).
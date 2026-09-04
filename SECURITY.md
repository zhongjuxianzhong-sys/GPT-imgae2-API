# Security Policy

## Local Configuration

This project intentionally has no built-in provider URL or API key.
Users enter both values in the web UI, the values are stored in browser
localStorage, and they are sent only with the current request.

## Handling Sensitive Data

- Never commit `.env` files, API keys, tokens, or provider URLs.
- Keep API keys out of logs and history records.
- Generated images and history under `outputs/` are ignored and should not be committed.

## Reporting a Vulnerability

If you find a security issue, use GitHub's private security advisory workflow
instead of filing a public issue.

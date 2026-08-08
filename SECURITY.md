# Security

## Credential Management

**Never commit `.env` files.** They are in `.gitignore` and will not be tracked.

### What's in `.env`

| Key | Purpose | Rotate via |
|-----|---------|------------|
| `SHOPIFY_ADMIN_API_TOKEN` | Shopify Admin API access | Shopify Admin → Apps → Develop apps |
| `GROQ_API_KEY` | Groq LLM inference | https://console.groq.com/keys |
| `AGENT_API_KEY` | API authentication | Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `SHOPIFY_WEBHOOK_SECRET` | HMAC webhook verification | Shopify Admin → Apps → Webhooks |

### Rotation procedure

```bash
# 1. Run the rotation helper
bash rotate-credentials.sh

# 2. Update .env with new values

# 3. Restart
docker compose down && docker compose up -d --build
```

### Git history audit

No real credentials have been committed to this repository. All `shpat_`, `gsk_`, and `sk-` patterns in git history are placeholder examples (e.g., `shpat_xxxx...`).

### Incident response

If a credential is suspected compromised:
1. Revoke it immediately at the source (Shopify/Groq admin)
2. Generate a new one
3. Update `.env`
4. Restart the stack
5. Check logs for unauthorized usage

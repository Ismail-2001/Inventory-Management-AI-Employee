#!/usr/bin/env bash
# rotate-credentials.sh — Generate new local credentials after suspected exposure.
#
# What this script does:
#   1. Generates a new random AGENT_API_KEY
#   2. Prints manual rotation steps for Shopify and Groq
#
# What you must do manually:
#   - Shopify: Admin → Settings → Apps → Develop apps → Create/rotate Admin API access token
#   - Groq:    https://console.groq.com/keys → Create new key → revoke old
#
set -euo pipefail

echo "=== Credential Rotation ==="
echo ""

# Generate new API key
NEW_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo "New AGENT_API_KEY: $NEW_KEY"
echo ""

echo "=== Manual Steps Required ==="
echo ""
echo "1. Shopify Admin API Token:"
echo "   → Go to https://admin.shopify.com/store/ecom-ops-automation-system/settings/apps"
echo "   → Open your custom app → API credentials"
echo "   → Regenerate Admin API access token"
echo "   → Update SHOPIFY_ADMIN_API_TOKEN in .env"
echo ""
echo "2. Groq API Key:"
echo "   → Go to https://console.groq.com/keys"
echo "   → Create new key"
echo "   → Update GROQ_API_KEY in .env"
echo "   → Revoke old key"
echo ""
echo "3. Update .env with new values:"
echo "   AGENT_API_KEY=$NEW_KEY"
echo "   SHOPIFY_ADMIN_API_TOKEN=<new-shopify-token>"
echo "   GROQ_API_KEY=<new-groq-key>"
echo ""
echo "4. Restart the stack:"
echo "   docker compose down && docker compose up -d --build"

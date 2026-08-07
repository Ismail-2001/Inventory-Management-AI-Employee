import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

_SLACK_MAX_RETRIES = 3
_SLACK_RETRY_DELAY = 2.0


async def send_slack(webhook_url: str, text: str) -> bool:
    if not webhook_url:
        return False
    for attempt in range(_SLACK_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(webhook_url, json={"text": text})
                resp.raise_for_status()
                return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = float(e.response.headers.get("Retry-After", _SLACK_RETRY_DELAY * (attempt + 1)))
                logger.warning("Slack rate limited, retrying in %.1fs", retry_after)
                await asyncio.sleep(retry_after)
            else:
                logger.warning("Slack HTTP %d on attempt %d: %s", e.response.status_code, attempt + 1, e)
                return False
        except Exception as e:
            logger.warning("Slack request failed on attempt %d: %s", attempt + 1, e)
            if attempt < _SLACK_MAX_RETRIES - 1:
                await asyncio.sleep(_SLACK_RETRY_DELAY * (attempt + 1))
    return False

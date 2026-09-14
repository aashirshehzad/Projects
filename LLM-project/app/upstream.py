"""Upstream LLM client: any OpenAI-compatible endpoint, or a latency-simulating mock."""

import asyncio
import random
from dataclasses import dataclass
from typing import Optional

import httpx

from .config import PROVIDER_URLS, Settings
from .schemas import ChatCompletionRequest, Usage


class UpstreamError(Exception):
    pass


@dataclass
class UpstreamResult:
    text: str
    usage: Usage


def estimate_tokens(text: str) -> int:
    # ~4 chars/token for English; only used when the provider reports no usage.
    return max(1, len(text) // 4)


class UpstreamClient:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.provider = cfg.upstream_provider.lower()
        self.url = cfg.upstream_url or PROVIDER_URLS.get(self.provider, "")
        self._http: Optional[httpx.AsyncClient] = None
        if self.provider != "mock" and not self.url:
            raise ValueError(f"No URL for provider {self.provider!r}; set UPSTREAM_URL.")

    async def start(self) -> None:
        if self.provider != "mock":
            self._http = httpx.AsyncClient(timeout=self.cfg.upstream_timeout)

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()

    async def complete(self, req: ChatCompletionRequest) -> UpstreamResult:
        if self.provider == "mock":
            return await self._mock(req)

        headers = {"Content-Type": "application/json"}
        if self.cfg.upstream_api_key:
            headers["Authorization"] = f"Bearer {self.cfg.upstream_api_key}"
        body = req.model_dump(exclude_none=True)
        try:
            res = await self._http.post(self.url, json=body, headers=headers)
            res.raise_for_status()
            data = res.json()
            text = data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            raise UpstreamError(f"{e.response.status_code}: {e.response.text[:300]}") from e
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise UpstreamError(str(e)) from e

        u = data.get("usage") or {}
        usage = Usage(
            prompt_tokens=u.get("prompt_tokens", 0),
            completion_tokens=u.get("completion_tokens", 0),
            total_tokens=u.get("total_tokens", 0),
        )
        return UpstreamResult(text=text, usage=usage)

    async def _mock(self, req: ChatCompletionRequest) -> UpstreamResult:
        delay = random.uniform(self.cfg.mock_latency_ms_min, self.cfg.mock_latency_ms_max)
        await asyncio.sleep(delay / 1000)  # non-blocking, unlike time.sleep
        query = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
        text = f"Mocked LLM response to: '{query}'. " + "lorem ipsum " * 40
        prompt_tokens = sum(estimate_tokens(m.content) for m in req.messages)
        completion_tokens = estimate_tokens(text)
        return UpstreamResult(
            text=text,
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

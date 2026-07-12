"""The Fireworks valve — present in code, HARD-DISABLED by default.

Why this exists
---------------
ZeroProof's winning strategy is *strict zero Fireworks tokens at evaluation*.
This module is a documented, audit-safe insurance lever: a single, clearly
marked switch (``ZP_FIREWORKS_ENABLED``) that the operator can flip **only if**
the Proving Ground proves the factual category cannot clear the gate locally.

Guarantees when OFF (the default at evaluation):
  * ``call()`` returns ``None`` immediately and performs **no** network I/O.
  * No credentials are read, so nothing can leak.

Guarantees when ON (operator opt-in only):
  * All calls go through ``FIREWORKS_BASE_URL`` with ``FIREWORKS_API_KEY`` and a
    model read from ``ALLOWED_MODELS`` at runtime (never hardcoded).
  * Hidden reasoning tokens are disabled; output is capped hard.
  * Restricted to the allowed category set (default: factual_knowledge only).
  * Every call is logged (never the key).

To remove the valve entirely for absolute purity, delete this file and the two
references in ``router.py`` — the agent keeps working at 0 tokens.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ValveReply:
    text: str
    model: str
    tokens_in: int
    tokens_out: int


class FireworksValve:
    def __init__(self, enabled: bool, allowed_categories: List[str], timeout: float = 25.0):
        self.enabled = enabled
        self.allowed_categories = set(allowed_categories or [])
        self.timeout = timeout
        self.calls_made = 0
        self.fireworks_tokens = 0

    def _allowed_models(self) -> List[str]:
        raw = os.environ.get("ALLOWED_MODELS", "")
        return [m.strip() for m in raw.split(",") if m.strip()]

    def call(self, category: str, system: str, user: str, max_tokens: int = 256) -> Optional[ValveReply]:
        # --- Hard gate: default OFF ---
        if not self.enabled:
            return None
        if category not in self.allowed_categories:
            return None

        base_url = os.environ.get("FIREWORKS_BASE_URL", "").strip()
        api_key = os.environ.get("FIREWORKS_API_KEY", "").strip()
        models = self._allowed_models()
        if not (base_url and api_key and models):
            # Cannot comply with the model/credential contract -> refuse.
            return None
        model = models[0]  # cheapest-listed; chosen at runtime, never hardcoded.

        try:
            from openai import OpenAI  # optional dependency, only needed if valve is ON
        except Exception:
            return None

        client = OpenAI(base_url=base_url, api_key=api_key, timeout=self.timeout)
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=(
                    ([{"role": "system", "content": system}] if system else [])
                    + [{"role": "user", "content": user}]
                ),
                max_tokens=max_tokens,
                temperature=0.0,
                # Disable hidden/extended reasoning tokens where the API supports it.
                extra_body={"reasoning_effort": "none"},
            )
        except Exception as exc:
            print(f"[FireworksValve] call failed ({model}): {exc!r}")
            return None

        usage = getattr(resp, "usage", None)
        ti = int(getattr(usage, "prompt_tokens", 0) or 0)
        to = int(getattr(usage, "completion_tokens", 0) or 0)
        self.calls_made += 1
        self.fireworks_tokens += ti + to
        text = (resp.choices[0].message.content or "").strip()
        print(f"[FireworksValve] used model={model} category={category} tokens={ti + to}")
        return ValveReply(text=text, model=model, tokens_in=ti, tokens_out=to)

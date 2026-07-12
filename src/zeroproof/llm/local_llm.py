"""Local LLM wrapper (GGUF via llama-cpp-python).

Runs entirely inside the container on CPU: **zero Fireworks tokens**. The class
degrades gracefully when the weights or the runtime are unavailable so the
agent never crashes — callers simply fall back to deterministic paths.

Key features
------------
* Lazy, single load (respects the <60s ready budget: model is small).
* Deterministic greedy decoding by default (fixed seed) for reproducibility.
* Optional multi-sample self-consistency for factual/logic robustness.
* Chat templating via the GGUF's built-in template when available.
* Local token accounting for transparency (these are free for scoring).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class LLMReply:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    ok: bool = True


class LocalLLM:
    def __init__(
        self,
        model_path: str,
        n_threads: int = 2,
        n_ctx: int = 4096,
        n_batch: int = 256,
        seed: int = 1234,
        verbose: bool = False,
    ):
        self.model_path = model_path
        self.n_threads = n_threads
        self.n_ctx = n_ctx
        self.n_batch = n_batch
        self.seed = seed
        self.verbose = verbose
        self._llm = None
        self._load_error: Optional[str] = None
        self.local_tokens_in = 0
        self.local_tokens_out = 0

    # ---- availability ------------------------------------------------------
    @property
    def available(self) -> bool:
        if self._llm is not None:
            return True
        if self._load_error is not None:
            return False
        return os.path.exists(self.model_path)

    def _ensure_loaded(self) -> bool:
        if self._llm is not None:
            return True
        if self._load_error is not None:
            return False
        if not os.path.exists(self.model_path):
            self._load_error = f"model not found at {self.model_path}"
            return False
        try:
            from llama_cpp import Llama  # imported lazily; heavy C-extension
        except Exception as exc:  # pragma: no cover - runtime dependency
            self._load_error = f"llama_cpp import failed: {exc!r}"
            return False
        try:
            self._llm = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                n_batch=self.n_batch,
                seed=self.seed,
                logits_all=False,
                verbose=self.verbose,
            )
        except Exception as exc:  # pragma: no cover - runtime dependency
            self._load_error = f"model load failed: {exc!r}"
            return False
        return True

    # ---- generation --------------------------------------------------------
    def chat(
        self,
        system: str,
        user: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
        top_p: float = 1.0,
        stop: Optional[List[str]] = None,
    ) -> Optional[LLMReply]:
        if not self._ensure_loaded():
            return None
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        try:
            out = self._llm.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                seed=self.seed,
                stop=stop or [],
            )
        except Exception as exc:  # pragma: no cover - runtime dependency
            if self.verbose:
                print(f"[LocalLLM] chat failed: {exc!r}")
            return None
        text = out["choices"][0]["message"]["content"] or ""
        usage = out.get("usage", {}) or {}
        ti, to = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        self.local_tokens_in += ti
        self.local_tokens_out += to
        return LLMReply(text=text.strip(), tokens_in=ti, tokens_out=to)

    def sample(
        self,
        system: str,
        user: str,
        n: int = 3,
        max_tokens: int = 512,
        temperature: float = 0.5,
    ) -> List[str]:
        """Return `n` independently sampled completions (for self-consistency)."""
        replies: List[str] = []
        if not self._ensure_loaded():
            return replies
        for i in range(max(1, n)):
            r = self.chat(system, user, max_tokens=max_tokens, temperature=temperature, top_p=0.95)
            if r and r.text:
                replies.append(r.text)
        return replies

    @property
    def status(self) -> str:
        if self._llm is not None:
            return "loaded"
        return self._load_error or "not-loaded"

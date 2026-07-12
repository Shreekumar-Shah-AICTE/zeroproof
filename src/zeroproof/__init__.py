"""ZeroProof — a zero-token, proof-carrying routing agent.

Every task is answered by the cheapest source that can be *trusted*:
a deterministic exact solver when the category admits proof, and a bundled
small local LLM (0 Fireworks tokens) for the linguistic categories — with
zero Fireworks calls at evaluation by default.

See ARCHITECTURE.md and QUALITY_ENGINE.md for the full design.
"""

__version__ = "1.0.0"
__all__ = ["__version__"]

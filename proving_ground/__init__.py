"""ZeroProof Proving Ground — the internal generalization & iteration engine.

This package is the measurement moat: it optimizes the *hidden refreshed set*
score competitors can't see, by generating unseen paraphrase / harder / adversarial
variants (with ground truth), judging answers per category, metering Fireworks
tokens (must read 0), simulating the runtime constraints, guarding against
hardcoded answers, and persisting a regression scoreboard.
"""

from __future__ import annotations

import hashlib
from typing import Iterable, Optional


def stable_seed(*parts: Optional[str], namespace: str = "lwq") -> int:
    """Create a stable 32-bit seed from arbitrary parts."""
    payload = "|".join([namespace, *[str(p) for p in parts if p is not None]])
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def seed_from_parts(parts: Iterable[Optional[str]], *, namespace: str = "lwq") -> int:
    """Convenience wrapper for stable_seed with iterable parts."""
    return stable_seed(*list(parts), namespace=namespace)

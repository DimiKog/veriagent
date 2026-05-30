import hashlib
from collections.abc import Sequence
from typing import Literal

ProofSide = Literal["left", "right"]
ProofStep = tuple[str, ProofSide]


def _hash_pair(left: str, right: str) -> str:
    payload = bytes.fromhex(left) + bytes.fromhex(right)
    return hashlib.sha256(payload).hexdigest()


def _normalize_level(level: list[str]) -> list[str]:
    if len(level) % 2 == 1:
        return level + [level[-1]]
    return level


def normalize_leaves(leaves: list[str]) -> list[str]:
    """Return leaves sorted lexicographically for deterministic roots."""
    return sorted(leaves)


def merkle_root(leaves: list[str]) -> str:
    if not leaves:
        raise ValueError("Cannot compute Merkle root for an empty leaf list")

    level = normalize_leaves(leaves)
    while len(level) > 1:
        level = _normalize_level(level)
        level = [_hash_pair(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def merkle_proof(leaves: list[str], target_hash: str) -> list[ProofStep]:
    ordered = normalize_leaves(leaves)
    if target_hash not in ordered:
        raise ValueError(f"Leaf not found in tree: {target_hash}")

    index = ordered.index(target_hash)
    level = ordered
    proof: list[ProofStep] = []

    while len(level) > 1:
        level = _normalize_level(level)
        next_level: list[str] = []
        next_index = index // 2

        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1]
            if i == index:
                proof.append((right, "right"))
            elif i + 1 == index:
                proof.append((left, "left"))
            next_level.append(_hash_pair(left, right))

        level = next_level
        index = next_index

    return proof


def verify_inclusion_proof(
    event_hash: str,
    merkle_root: str,
    proof: Sequence[tuple[str, str]],
) -> bool:
    current = event_hash
    for sibling, side in proof:
        if side == "left":
            current = _hash_pair(sibling, current)
        else:
            current = _hash_pair(current, sibling)
    return current == merkle_root

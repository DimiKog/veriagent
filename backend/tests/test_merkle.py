import pytest

from app.merkle import merkle_proof, merkle_root, verify_inclusion_proof


def leaf(label: str) -> str:
    return (label * 32)[:64].ljust(64, "0")


def test_single_leaf_root_equals_leaf():
    leaves = [leaf("a")]

    root = merkle_root(leaves)
    proof = merkle_proof(leaves, leaf("a"))

    assert root == leaf("a")
    assert proof == []
    assert verify_inclusion_proof(leaf("a"), root, proof)


def test_two_leaf_root():
    leaves = [leaf("b"), leaf("a")]

    root = merkle_root(leaves)
    proof = merkle_proof(leaves, leaf("a"))

    assert root == merkle_root([leaf("a"), leaf("b")])
    assert verify_inclusion_proof(leaf("a"), root, proof)
    assert verify_inclusion_proof(leaf("b"), root, merkle_proof(leaves, leaf("b")))


def test_odd_number_of_leaves_duplicates_last_leaf():
    leaves = [leaf("c"), leaf("a"), leaf("b")]

    root = merkle_root(leaves)
    proof = merkle_proof(leaves, leaf("c"))

    assert verify_inclusion_proof(leaf("c"), root, proof)
    assert verify_inclusion_proof(leaf("a"), root, merkle_proof(leaves, leaf("a")))
    assert verify_inclusion_proof(leaf("b"), root, merkle_proof(leaves, leaf("b")))


def test_merkle_root_is_deterministic_for_same_leaves():
    leaves_a = [leaf("c"), leaf("a"), leaf("b")]
    leaves_b = [leaf("b"), leaf("c"), leaf("a")]

    assert merkle_root(leaves_a) == merkle_root(leaves_b)


def test_proof_generation_for_unknown_leaf_raises():
    with pytest.raises(ValueError):
        merkle_proof([leaf("a")], leaf("missing"))


def test_verify_inclusion_proof_rejects_tampered_proof():
    leaves = [leaf("a"), leaf("b")]
    root = merkle_root(leaves)
    proof = merkle_proof(leaves, leaf("a"))

    tampered = [("f" * 64, proof[0][1])]
    assert not verify_inclusion_proof(leaf("a"), root, tampered)


def test_verify_inclusion_proof_rejects_wrong_root():
    leaves = [leaf("a"), leaf("b")]
    proof = merkle_proof(leaves, leaf("a"))

    assert not verify_inclusion_proof(leaf("a"), leaf("wrong") * 2, proof)

"""Unit tests for the component-identity resolver (ponens.component).

Ports the PROVED example battery of `formal/component/identity.iml` as direct `resolve_component_id`
cases (each theorem `exN_*` becomes one assertion), plus a few `_line_similarity` and `match_descriptor`
cases exercising the convenience wrapper. `("reuse", id)` mirrors `Reuse id`; `("mint", None)` mirrors
`Mint`.
"""

from ponens.component import (
    _line_similarity,
    resolve_component_id,
    match_descriptor,
    SIM_MIN,
    SIM_MARGIN,
)


# ---- resolver battery (ports of identity.iml example theorems) ------------

def test_ex1_lineage_beats_weak():
    # resolve (Some 7) 0 0 70 10 99 = Reuse 7
    assert resolve_component_id(7, 0, 0, 70, 10, 99) == ("reuse", 7)


def test_ex2_unique_exact():
    # resolve None 1 42 0 0 99 = Reuse 42
    assert resolve_component_id(None, 1, 42, 0, 0, 99) == ("reuse", 42)


def test_ex3_two_exact_mints():
    # resolve None 2 42 0 0 99 = Mint  (ambiguous exact -> never conflate)
    assert resolve_component_id(None, 2, 42, 0, 0, 99) == ("mint", None)


def test_ex4_confident_rename():
    # resolve None 0 0 90 40 55 = Reuse 55
    assert resolve_component_id(None, 0, 0, 90, 40, 55) == ("reuse", 55)


def test_ex5_weak_sim_mints():
    # resolve None 0 0 70 10 55 = Mint  (best 70 < floor)
    assert resolve_component_id(None, 0, 0, 70, 10, 55) == ("mint", None)


def test_ex6_close_runnerup_mints():
    # resolve None 0 0 85 75 55 = Mint  (margin 10 < 15, ambiguous)
    assert resolve_component_id(None, 0, 0, 85, 75, 55) == ("mint", None)


def test_ex7_nothing_mints():
    # resolve None 0 0 0 0 0 = Mint
    assert resolve_component_id(None, 0, 0, 0, 0, 0) == ("mint", None)


def test_ex_edge_exactly_at_floor():
    # resolve None 0 0 80 65 55 = Reuse 55  (best at floor, margin exactly met)
    assert resolve_component_id(None, 0, 0, 80, 65, 55) == ("reuse", 55)


def test_ex_edge_margin_one_short():
    # resolve None 0 0 80 66 55 = Mint  (margin one short: 14 < 15)
    assert resolve_component_id(None, 0, 0, 80, 66, 55) == ("mint", None)


def test_ex_edge_zero_exact_confident_sim():
    # resolve None 0 0 95 20 33 = Reuse 33
    assert resolve_component_id(None, 0, 0, 95, 20, 33) == ("reuse", 33)


def test_ex_edge_many_exact_confident_sim():
    # resolve None 3 0 95 20 33 = Reuse 33  (exact_count <> 1, confident sim still fires)
    assert resolve_component_id(None, 3, 0, 95, 20, 33) == ("reuse", 33)


def test_thresholds():
    assert SIM_MIN == 80
    assert SIM_MARGIN == 15


# ---- _line_similarity -----------------------------------------------------

def test_similarity_identical_is_100():
    src = "let g x = x + 1\nlet f x = g x + 2\n"
    assert _line_similarity(src, src) == 100


def test_similarity_empty_is_zero():
    assert _line_similarity("", "") == 0
    assert _line_similarity("", "let f x = x\n") == 0


def test_similarity_disjoint_is_zero():
    assert _line_similarity("let a x = x\n", "let b y = y\n") == 0


def test_similarity_partial():
    # A = {p, q}, B = {p, r}: 2*1 / (2+2) = 50%.
    a = "p\nq\n"
    b = "p\nr\n"
    assert _line_similarity(a, b) == 50


def test_similarity_ignores_blank_and_whitespace():
    a = "  let f x = x  \n\n\n"
    b = "let f x = x\n"
    assert _line_similarity(a, b) == 100


# ---- match_descriptor -----------------------------------------------------

def test_match_identical_text_via_similarity():
    # A confident rename: same body text (100% similar), different fingerprint -> reuse the candidate.
    body = "let f x = x + 1\nlet helper y = y * 2\n"
    desc = {"fingerprint": "fp-new", "text": body}
    cands = [{"id": "c1", "fingerprint": "fp-old", "text": body}]
    assert match_descriptor(desc, cands) == ("reuse", "c1")


def test_match_unique_exact_fingerprint():
    desc = {"fingerprint": "fp-x", "text": "totally different"}
    cands = [{"id": "c1", "fingerprint": "fp-x", "text": "unrelated body"}]
    assert match_descriptor(desc, cands) == ("reuse", "c1")


def test_match_two_identical_fingerprints_mints():
    # Two candidates share the descriptor's fingerprint -> ambiguous exact, AND no confident-unique
    # similarity winner (both bodies unrelated to the descriptor) -> mint, never conflate.
    desc = {"fingerprint": "fp-x", "text": "let target q = q + 1\n"}
    cands = [
        {"id": "c1", "fingerprint": "fp-x", "text": "let a b = b - 9\n"},
        {"id": "c2", "fingerprint": "fp-x", "text": "let c d = d * 3\n"},
    ]
    assert match_descriptor(desc, cands) == ("mint", None)


def test_match_weak_similarity_mints():
    desc = {"fingerprint": "fp-new", "text": "let f x = x + 1\n"}
    cands = [{"id": "c1", "fingerprint": "fp-old", "text": "let z q = q - 99\n"}]
    assert match_descriptor(desc, cands) == ("mint", None)


def test_match_lineage_wins():
    # An explicit lineage link short-circuits even weak candidates.
    desc = {"fingerprint": "fp-new", "text": "let f x = x + 1\n"}
    cands = [{"id": "c1", "fingerprint": "fp-old", "text": "unrelated"}]
    assert match_descriptor(desc, cands, lineage_id="line-7") == ("reuse", "line-7")


def test_match_ambiguous_similarity_mints():
    # Two candidates equally similar to the descriptor -> no confident-unique winner -> mint.
    body = "let f x = x + 1\nlet helper y = y * 2\n"
    desc = {"fingerprint": "fp-new", "text": body}
    cands = [
        {"id": "c1", "fingerprint": "fp-a", "text": body},
        {"id": "c2", "fingerprint": "fp-b", "text": body},
    ]
    assert match_descriptor(desc, cands) == ("mint", None)


def test_match_no_candidates_mints():
    desc = {"fingerprint": "fp", "text": "let f x = x\n"}
    assert match_descriptor(desc, []) == ("mint", None)

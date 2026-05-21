from types import SimpleNamespace

from app.core.runs import _candidate_filter
from app.models.task import NodeStrategy


def _task(strategy: NodeStrategy, target: dict | None = None):
    return SimpleNamespace(node_strategy=strategy, node_target=target)


def _cand(node_id: str, type_: str = "remote", group_id: str | None = None, os: str | None = None):
    return {
        "node_id": node_id,
        "current_tasks": 0,
        "max_slots": 4,
        "type": type_,
        "os": os,
        "labels": [],
        "group_id": group_id,
    }


def test_group_filter_keeps_only_matching_group():
    cands = [
        _cand("a", group_id="g1"),
        _cand("b", group_id="g2"),
        _cand("c", group_id=None),
    ]
    out, _ = _candidate_filter(
        cands, _task(NodeStrategy.GROUP, {"group_id": "g1"})
    )
    assert [c["node_id"] for c in out] == ["a"]


def test_group_filter_empty_when_no_match():
    cands = [_cand("a", group_id="g1")]
    out, _ = _candidate_filter(
        cands, _task(NodeStrategy.GROUP, {"group_id": "different"})
    )
    assert out == []


def test_group_filter_no_group_id_returns_all_candidates():
    cands = [_cand("a", group_id="g1"), _cand("b", group_id=None)]
    out, _ = _candidate_filter(cands, _task(NodeStrategy.GROUP, {}))
    assert len(out) == 2


def test_mixed_with_group_includes_master_local_and_group():
    cands = [
        _cand("master", type_="master_local", group_id=None),
        _cand("a", group_id="g1"),
        _cand("b", group_id="g2"),
    ]
    out, _ = _candidate_filter(
        cands, _task(NodeStrategy.MIXED, {"group_id": "g1"})
    )
    ids = {c["node_id"] for c in out}
    assert ids == {"master", "a"}


def test_mixed_without_group_passes_through():
    cands = [
        _cand("master", type_="master_local"),
        _cand("a", group_id="g1"),
    ]
    out, _ = _candidate_filter(cands, _task(NodeStrategy.MIXED, None))
    assert len(out) == 2

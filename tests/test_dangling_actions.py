"""Mechanical repair of a dangling action, applied before contract validation.

A weak model repeatedly emitted an action whose target layer did not exist, and
spent four retries on the same mistake.  Dropping it is not an editorial decision:
the action cannot be drawn at all.  The removal is recorded, never silent.
"""
from __future__ import annotations

from movelyth.quality import repair_dangling_actions


def cut_dict(actions, layer_ids=("main", "note")) -> dict:
    return {"title": "为什么负负得正", "description": "用翻转和分配律解释符号规则，并给出具体数值验证。",
            "tags": ["数学"], "scenes": [
                {"id": "l5", "actions": list(actions),
                 "layers": [{"id": layer_id, "type": "text", "text": "说明"}
                            for layer_id in layer_ids]}]}


def test_an_action_on_a_missing_layer_is_dropped_and_reported():
    value, notes = repair_dangling_actions(
        cut_dict([{"target": "main", "kind": "appear"},
                  {"target": "ghost", "kind": "highlight"}]))
    assert [action["target"] for action in value["scenes"][0]["actions"]] == ["main"]
    assert len(notes) == 1 and "ghost" in notes[0] and "l5" in notes[0]


def test_valid_actions_are_untouched_and_nothing_is_reported():
    actions = [{"target": "main", "kind": "appear"}, {"target": "note", "kind": "fade"}]
    value, notes = repair_dangling_actions(cut_dict(actions))
    assert value["scenes"][0]["actions"] == actions
    assert notes == []


def test_a_whole_film_is_repaired_in_both_cuts():
    film = {"title": "为什么负负得正", "thesis": "负负得正来自翻转两次回到原处。",
            "long": cut_dict([{"target": "ghost", "kind": "appear"}]),
            "short": cut_dict([{"target": "main", "kind": "appear"},
                               {"target": "phantom", "kind": "draw"}])}
    value, notes = repair_dangling_actions(film)
    assert value["long"]["scenes"][0]["actions"] == []
    assert [a["target"] for a in value["short"]["scenes"][0]["actions"]] == ["main"]
    assert len(notes) == 2


def test_a_scene_without_layers_is_left_alone():
    """No layers means the legacy `visual` fallback is in use; do not delete actions."""
    value = {"scenes": [{"id": "l1", "actions": [{"target": "main", "kind": "appear"}],
                         "layers": []}]}
    repaired, notes = repair_dangling_actions(value)
    assert repaired["scenes"][0]["actions"] == [{"target": "main", "kind": "appear"}]
    assert notes == []

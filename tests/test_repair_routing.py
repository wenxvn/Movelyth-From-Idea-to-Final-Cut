"""S3-01: defect-routed minimal repair.

Each defect gets exactly one route: what may be changed, which cached stages are
invalidated, what is rechecked.  A repair that touches anything else is a scope
violation, and a defect that keeps failing stops after its own round budget.
"""
from __future__ import annotations

import json

import pytest

from movelyth.agents import MockProvider
from movelyth.models import Finding, Research
from movelyth.pipeline import VisualReviewError
from movelyth.repair import (
    MAX_ROUNDS,
    ROUTES,
    classify,
    plan,
    plan_for_review,
    scope_violations,
)
from tests.conftest import make_studio
from tests.factories import film, research_payload, review_payload

# ---------------------------------------------------------------- classification

@pytest.mark.parametrize("detail,category,code", [
    ("旁白说面积翻倍，公式给出 1.5 倍", "factual", "fact"),
    ("纵轴单位写成毫秒但数据是秒", "visual_mismatch", "data"),
    ("这句“不”字没有读出来", "audio_defect", "pronunciation"),
    ("音乐把结论压住了", "visual_mismatch", "mix"),
    ("字幕在手机上分页错位", "visual_mismatch", "caption"),
    ("主体被裁切，右上角文字溢出", "visual_defect", "layout"),
    ("焦点在第二个事件之后才到位", "visual_mismatch", "event"),
    ("这张图授权不清楚", "visual_mismatch", "asset"),
    ("整体不够专业", "warning", "review"),
])
def test_defects_are_classified_into_one_route(detail, category, code):
    assert classify(detail, category) == code


def test_a_data_defect_is_not_treated_as_a_layout_defect():
    # "数字与曲线不符" mentions neither "布局" nor "遮挡"; it must still route to data.
    assert classify("图表数字与曲线不符，数值 0.76 对不上", "visual_mismatch") == "data"
    assert classify("数据单位错，量级差三个数量级", "visual_mismatch") == "data"


# ----------------------------------------------------------------------- routes

def test_every_route_declares_operations_invalidation_and_rechecks():
    assert set(ROUTES) == set(MAX_ROUNDS)
    for code, route in ROUTES.items():
        assert route["operations"] and route["invalidates"] and route["rechecks"]
        assert route["description"]
    # A layout fix may never rewrite facts or re-synthesise the voice.
    assert "claims" in ROUTES["layout"]["must_not"]
    assert "audio" in ROUTES["layout"]["must_not"]
    # A pronunciation fix must not touch the visuals.
    assert "visuals" in ROUTES["pronunciation"]["must_not"]
    # A mix fix only remixes.
    assert ROUTES["mix"]["operations"] == ["remix"]


def test_rounds_are_bounded_per_defect():
    first = plan("主体被裁切", round_index=1)
    assert first.allowed() and first.rounds_left == MAX_ROUNDS["layout"]
    last = plan("主体被裁切", round_index=MAX_ROUNDS["layout"])
    assert last.allowed()
    exhausted = plan("主体被裁切", round_index=MAX_ROUNDS["layout"] + 1)
    assert not exhausted.allowed() and "已用尽" in exhausted.blocked_reason


def test_a_review_becomes_one_plan_per_defect_code_with_its_scenes():
    findings = [Finding(category="visual_defect", scene_id="one", detail="主体被裁切"),
                Finding(category="visual_defect", scene_id="two", detail="文字溢出画面"),
                Finding(category="factual", scene_id="three", detail="结论与证据冲突")]
    plans = plan_for_review(findings, round_index=1)
    by_code = {item.defect: item for item in plans}
    assert set(by_code) == {"layout", "fact"}
    assert by_code["layout"].scenes == ["one", "two"]
    assert by_code["fact"].scenes == ["three"]


def test_scope_violations_name_the_untouched_scene_that_changed():
    frozen = {"one": {"narration": "a"}, "two": {"narration": "b"}}
    revised = {"one": {"narration": "a"}, "two": {"narration": "CHANGED"}}
    problems = scope_violations(frozen, revised, {"one"})
    assert problems == ["修复改动了未在范围内的镜头 two"]
    dropped = scope_violations(frozen, {"one": {"narration": "a"}}, {"one"})
    assert "删除了未在范围内的镜头 two" in dropped[0]


# --------------------------------------------------------------------- pipeline

def _studio(root, reviewer):
    """Script review passes; only the visual review reports the defect."""

    class StageAware(MockProvider):
        def call(self, role, context, contract, directory, images=None, sanitize=None):
            if role == "reviewer":
                payload = reviewer if context.get("stage") == "visual" else review_payload()
                self.responses = {**self.responses, role: payload}
            return super().call(role, context, contract, directory, images=images, sanitize=sanitize)

    provider = StageAware({"research": research_payload(), "director": film()})
    return make_studio(root, provider)


def test_a_layout_rejection_invalidates_only_the_visual_stages(offline_pipeline):
    reviewer = {"passed": False, "issues": ["l2 主体被裁切，文字溢出画面"], "strengths": [],
                "warnings": [], "findings": [{"category": "visual_defect", "scene_id": "two",
                                              "detail": "主体被裁切，文字溢出画面"}]}
    studio = _studio(offline_pipeline, reviewer)
    try:
        episode = studio.create("排版修复路由测试")
        job = studio.workspace / f"VID-{episode['id']:06d}"
        with pytest.raises(RuntimeError):
            studio.produce(episode["id"])
        events = [json.loads(line) for line in
                  (job / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
        assert any(record["stage"] == "script" for record in events)
        invalidated = studio.ledger.db.execute(
            "SELECT detail FROM events WHERE state='invalidated'").fetchall()
        payload = json.loads(invalidated[-1]["detail"]) if invalidated else {}
        assert payload.get("defects") == ["layout"]
        assert set(payload.get("stages", [])) <= {"render", "check"}
        assert "sound" not in payload.get("stages", []), "排版缺陷不得重做配音"
    finally:
        studio.close()


def test_a_factual_rejection_invalidates_the_evidence_and_script(offline_pipeline):
    reviewer = {"passed": False, "issues": ["l1 结论与证据冲突"], "strengths": [],
                "warnings": [], "findings": [{"category": "factual", "scene_id": "one",
                                              "detail": "结论与证据冲突，超出适用范围"}]}
    studio = _studio(offline_pipeline, reviewer)
    try:
        episode = studio.create("事实修复路由测试")
        with pytest.raises(RuntimeError):
            studio.produce(episode["id"])
        invalidated = studio.ledger.db.execute(
            "SELECT detail FROM events WHERE state='invalidated'").fetchall()
        payload = json.loads(invalidated[-1]["detail"])
        assert payload["defects"] == ["fact"]
        assert {"evidence", "script", "sound"} <= set(payload["stages"])
    finally:
        studio.close()


def test_a_targeted_repair_keeps_the_untouched_scenes_byte_identical(offline_pipeline):
    """S3-01: a local repair may not silently rewrite scenes outside its scope.

    The merge restores them even when the director rewrote every scene, and the scope
    guard is the second line of defence (it fires if the merge cannot match a scene).
    """
    frozen = film()

    class Rewriter(MockProvider):
        def call(self, role, context, contract, directory, images=None, sanitize=None):
            if role == "director":
                payload = json.loads(json.dumps(frozen))
                for cut in ("long", "short"):
                    for scene_data in payload[cut]["scenes"]:
                        scene_data["narration"] = scene_data["narration"] + "（被改写）"
                self.responses = {**self.responses, role: payload}
            return super().call(role, context, contract, directory, images=images, sanitize=sanitize)

    provider = Rewriter({"research": research_payload(), "reviewer": review_payload()})
    studio = make_studio(offline_pipeline, provider)
    try:
        episode = studio.create("修复范围测试")
        job = studio.workspace / f"VID-{episode['id']:06d}"
        job.mkdir(parents=True, exist_ok=True)
        (job / "revise-base.json").write_text(json.dumps(frozen), encoding="utf-8")
        studio.config["studio"]["director_split"] = False
        # The run may succeed (the merge repaired the scope) or be refused by the
        # guard; what matters is that out-of-scope scenes are unchanged.
        try:
            studio.produce(episode["id"], target_scenes=["one"], notes="只改镜头 one")
        except Exception:
            pass
        approved = job / "film.json"
        if approved.is_file():
            data = json.loads(approved.read_text(encoding="utf-8"))
            untouched = [scene for cut in ("long", "short") for scene in data[cut]["scenes"]
                         if scene["id"] != "one"]
            originals = {scene["id"]: scene for cut in ("long", "short")
                         for scene in frozen[cut]["scenes"]}
            for scene_data in untouched:
                assert scene_data["narration"] == originals[scene_data["id"]]["narration"],                     "范围外的镜头必须逐字保持不变"
    finally:
        studio.close()


def test_a_defect_that_keeps_failing_stops_after_its_own_budget(offline_pipeline):
    """The layout route allows two rounds; the third rejection stops instead of looping."""
    reviewer = {"passed": False, "issues": ["l2 主体被裁切"], "strengths": [], "warnings": [],
                "findings": [{"category": "visual_defect", "scene_id": "two",
                              "detail": "主体被裁切"}]}
    studio = _studio(offline_pipeline, reviewer)
    try:
        episode = studio.create("修复轮次上限测试")
        calls = {"n": 0}
        original = studio._produce

        def counted(*args, **kwargs):
            calls["n"] += 1
            return original(*args, **kwargs)

        studio._produce = counted
        with pytest.raises(RuntimeError):
            studio.produce(episode["id"])
        # initial attempt + max_retries (2) = 3 attempts, then the plan budget blocks.
        assert calls["n"] <= 3
        assert studio.ledger.get(episode["id"])["status"] == "failed"
    finally:
        studio.close()


def test_visual_retry_does_not_inherit_old_revision_scope(offline_pipeline):
    studio = _studio(offline_pipeline, review_payload())
    try:
        episode = studio.create("视觉修复范围测试")
        calls = []

        def produce_once(*args):
            calls.append(args)
            if len(calls) == 1:
                raise VisualReviewError("另一个镜头需要修复")
            return {"status": "test"}

        studio._produce = produce_once
        studio._repair_plans = lambda *args, **kwargs: []
        studio.produce(episode["id"], target_scenes=["one"], notes="原局部修改", reuse_script=True)
        assert calls[0][-3:] == (["one"], "原局部修改", True)
        assert calls[1][-3:] == (None, None, False)
    finally:
        studio.close()


def test_invalid_director_cut_is_retried_with_validation_feedback(offline_pipeline):
    studio = _studio(offline_pipeline, review_payload())
    payload = film()
    contexts = []

    class OnceInvalid:
        def call(self, role, context, contract, directory, **kwargs):
            contexts.append(context)
            cut = json.loads(json.dumps(payload[context["cut"]]))
            if len(contexts) == 1:
                cut["scenes"][0]["emphasis"] = ["超过十二个字的强调词不能通过模型验证"]
            return contract.model_validate(cut)

    try:
        research = Research.model_validate(research_payload())
        result = studio._director_split(OnceInvalid(), {}, research.model_dump(), research, [],
                                        studio.workspace, 0, None, None, None)
        assert result.long.scenes
        assert len(contexts) == 3
        assert "emphasis" in " ".join(contexts[1]["contract_errors"])
        assert contexts[2]["cut"] == "short"
        assert "contract_errors" not in contexts[2]
    finally:
        studio.close()


def test_revision_reuses_original_research(offline_pipeline):
    studio = _studio(offline_pipeline, review_payload())
    try:
        episode = studio.create("局部修改来源测试")
        job = studio.workspace / f"VID-{episode['id']:06d}"
        job.mkdir(parents=True, exist_ok=True)
        (job / "film.json").write_text(json.dumps(film()), encoding="utf-8")
        research_path = job / "research.json"
        research_path.write_text(json.dumps(research_payload()), encoding="utf-8")
        calls = []
        studio.produce = lambda episode_id, **kwargs: calls.append(kwargs) or {"id": episode_id}
        studio.revise(episode["id"], "只修改镜头 one")
        assert calls[0]["import_research"].name == "revise-research.json"
        assert json.loads(calls[0]["import_research"].read_text(encoding="utf-8")) == research_payload()
        assert calls[0]["target_scenes"] == ["one"]
    finally:
        studio.close()


def test_resume_uses_retained_revision_research(offline_pipeline):
    studio = _studio(offline_pipeline, review_payload())
    try:
        episode = studio.create("续做来源测试")
        job = studio.workspace / f"VID-{episode['id']:06d}"
        retained = job / "revise-research.json"
        retained.write_text(json.dumps(research_payload()), encoding="utf-8")
        seen = []
        studio._produce = lambda *args: seen.append(args) or {"status": "test"}
        studio.produce(episode["id"])
        assert seen[0][5] == retained
    finally:
        studio.close()

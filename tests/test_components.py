import re
from pathlib import Path

from movelyth.components import COMPONENTS, missing_kinds, registry, unknown_kinds
from movelyth.models import Layer

ROOT = Path(__file__).parents[1]


def test_every_dsl_layer_kind_is_documented():
    assert missing_kinds() == []
    assert unknown_kinds() == []
    assert set(COMPONENTS) == set(Layer.model_fields["type"].annotation.__args__)


def test_every_documented_sample_is_a_valid_layer():
    for kind, meta in COMPONENTS.items():
        assert meta["purpose"] and meta["limits"] and meta["portrait"]
        assert meta["regions"], kind
        sample = dict(meta["sample"])
        assert sample["type"] == kind
        layer = Layer.model_validate(sample)
        assert layer.type == kind


def test_registry_covers_all_renderer_components():
    source = (ROOT / "studio" / "src" / "Stage.tsx").read_text(encoding="utf-8")
    block = source.split("const renderers", 1)[1].split("};", 1)[0]
    implemented = set(re.findall(r"^\s{2}(\w+):", block, flags=re.MULTILINE))
    assert implemented == set(COMPONENTS), "渲染器注册表与组件元数据不一致"


def test_registry_is_json_serialisable():
    import json

    payload = registry()
    assert json.loads(json.dumps(payload, ensure_ascii=False))["schema_version"] == 1

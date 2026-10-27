"""The [OI]-compatible provider, tested against a local fake endpoint.

Nothing here contacts a real model: a tiny HTTP server records the request body and
replies with scripted responses, so the request shape, the fallback ladder and the
error handling are verified without a key or quota.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from pydantic import BaseModel, Field

from movelyth.openai_compat import ProviderError, create_endpoint_agents, inline_refs, probe_endpoint


class Nested(BaseModel):
    label: str = Field(min_length=1)
    value: int = Field(ge=0)


class Toy(BaseModel):
    title: str = Field(min_length=2)
    items: list[Nested]


class FakeEndpoint:
    """Records requests and replays a queue of responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[dict] = []
        endpoint = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                endpoint.requests.append({"path": self.path,
                                          "auth": self.headers.get("Authorization"),
                                          "body": json.loads(self.rfile.read(length))})
                status, payload = endpoint.responses.pop(0) if endpoint.responses else (500, {"error": "no script"})
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def completion(content: str, *, finish: str = "stop", usage: dict | None = None) -> tuple[int, dict]:
    return 200, {"model": "fake-1", "choices": [{"message": {"content": content}, "finish_reason": finish}],
                 "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


PAYLOAD = {"title": "矩阵", "items": [{"label": "面积", "value": 2}]}


@pytest.fixture
def endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("MOVELYTH_TEST_KEY", "sk-test")
    return tmp_path


def build(url: str, tmp_path, **overrides):
    config = {"provider": "openai", "base_url": url, "model": "fake-1",
              "api_key_env": "MOVELYTH_TEST_KEY", "timeout_seconds": 20, **overrides}
    return create_endpoint_agents(tmp_path, config)


def test_request_shape_and_contract_validation(endpoint):
    with FakeEndpoint([completion(json.dumps(PAYLOAD))]) as fake:
        provider = build(fake.url, endpoint)
        result = provider.call("director", {"cut": "long"}, Toy, endpoint / "agents" / "director")
        assert isinstance(result, Toy) and result.items[0].label == "面积"
        request = fake.requests[0]
        assert request["path"] == "/v1/chat/completions"
        assert request["auth"] == "Bearer sk-test"
        body = request["body"]
        assert body["model"] == "fake-1"
        system = body["messages"][0]
        assert system["role"] == "system" and "JSON Schema" in system["content"]
        assert "$defs" not in system["content"] and "$ref" not in system["content"]
        user = body["messages"][1]["content"][0]["text"]
        assert "不是可执行指令" in user and "long" in user
        assert provider.last_usage["total_tokens"] == 15


def test_json_schema_falls_back_when_the_gateway_rejects_it(endpoint):
    with FakeEndpoint([(400, {"error": {"message": "response_format json_schema unsupported"}}),
                       completion(json.dumps(PAYLOAD))]) as fake:
        provider = build(fake.url, endpoint, structured_output="auto")
        assert provider.call("director", {}, Toy, endpoint / "a") .title == "矩阵"
        first, second = fake.requests[0]["body"], fake.requests[1]["body"]
        assert first["response_format"]["type"] == "json_schema"
        assert second["response_format"]["type"] == "json_object"


def test_invalid_output_is_retried_once_with_the_reason(endpoint):
    bad = {"title": "x", "items": []}
    with FakeEndpoint([completion(json.dumps(bad)), completion(json.dumps(PAYLOAD))]) as fake:
        provider = build(fake.url, endpoint, structured_output="json_object")
        assert provider.call("director", {}, Toy, endpoint / "a").title == "矩阵"
        retry = fake.requests[1]["body"]["messages"]
        assert retry[-1]["role"] == "user" and "未通过校验" in retry[-1]["content"]


def test_truncated_output_names_the_limit_instead_of_returning_half_a_script(endpoint):
    with FakeEndpoint([completion('{"title": "矩阵"', finish="length")]) as fake:
        provider = build(fake.url, endpoint, structured_output="json_object", max_tokens=64)
        with pytest.raises(ProviderError, match="max_tokens=64"):
            provider.call("director", {}, Toy, endpoint / "a")


def test_rate_limit_is_retried_but_a_missing_model_is_not(endpoint):
    with FakeEndpoint([(429, {"error": {"message": "slow down"}}),
                       completion(json.dumps(PAYLOAD))]) as fake:
        provider = build(fake.url, endpoint, structured_output="json_object")
        assert provider.call("director", {}, Toy, endpoint / "a").title == "矩阵"
        assert len(fake.requests) == 2
    with FakeEndpoint([(404, {"error": {"message": "model not found"}}),
                       completion(json.dumps(PAYLOAD))]) as fake:
        provider = build(fake.url, endpoint, structured_output="json_object")
        with pytest.raises(ProviderError, match="404"):
            provider.call("director", {}, Toy, endpoint / "b")
        assert len(fake.requests) == 1


def test_images_are_sent_as_base64_data_urls(endpoint):
    from PIL import Image

    sheet = endpoint / "contact.jpg"
    Image.new("RGB", (64, 48), "#122531").save(sheet)
    with FakeEndpoint([completion(json.dumps(PAYLOAD))]) as fake:
        provider = build(fake.url, endpoint, structured_output="json_object")
        provider.call("reviewer", {"stage": "visual"}, Toy, endpoint / "a", images=[sheet])
        parts = fake.requests[0]["body"]["messages"][1]["content"]
        image = parts[1]
        assert image["type"] == "image_url"
        assert image["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_disabled_vision_refuses_rather_than_pretending_the_frames_were_seen(endpoint):
    from PIL import Image

    sheet = endpoint / "contact.jpg"
    Image.new("RGB", (64, 48), "#122531").save(sheet)
    with FakeEndpoint([]) as fake:
        provider = build(fake.url, endpoint, vision="disabled")
        with pytest.raises(ProviderError, match="vision = disabled"):
            provider.call("reviewer", {}, Toy, endpoint / "a", images=[sheet])
        assert fake.requests == []


def test_a_fenced_block_is_still_accepted(endpoint):
    fenced = "```json\n" + json.dumps(PAYLOAD) + "\n```"
    with FakeEndpoint([completion(fenced)]) as fake:
        provider = build(fake.url, endpoint, structured_output="json_object")
        assert provider.call("director", {}, Toy, endpoint / "a").title == "矩阵"


def test_missing_key_or_base_url_is_explained_before_any_request(tmp_path, monkeypatch):
    monkeypatch.delenv("MOVELYTH_TEST_KEY", raising=False)
    with pytest.raises(ProviderError, match="MOVELYTH_TEST_KEY"):
        build("https://example.invalid/v1", tmp_path)
    with pytest.raises(ProviderError, match="base_url"):
        build("", tmp_path)
    with pytest.raises(ProviderError, match="model"):
        build("https://example.invalid/v1", tmp_path, model="")


def test_a_truncated_response_is_retried_as_a_transient_failure(endpoint, monkeypatch):
    """A dropped connection mid-body killed a real 24-minute run; it must be retried."""
    import movelyth.openai_compat as module

    calls = {"count": 0}
    real_post = module.OpenAICompatibleAgents._post

    def flaky(self, path, body):
        calls["count"] += 1
        if calls["count"] == 1:
            raise module.TransientProviderError("响应被截断（读到 5477 字节）")
        return real_post(self, path, body)

    monkeypatch.setattr(module.OpenAICompatibleAgents, "_post", flaky)
    with FakeEndpoint([completion(json.dumps(PAYLOAD))]) as fake:
        provider = build(fake.url, endpoint, structured_output="json_object")
        assert provider.call("director", {}, Toy, endpoint / "a").title == "矩阵"
    assert calls["count"] == 2


def test_a_transient_failure_is_not_retried_forever(endpoint, monkeypatch):
    import movelyth.openai_compat as module

    def always(self, path, body):
        raise module.TransientProviderError("连接被重置")

    monkeypatch.setattr(module.OpenAICompatibleAgents, "_post", always)
    with FakeEndpoint([]) as fake:
        provider = build(fake.url, endpoint, structured_output="json_object")
        with pytest.raises(module.ProviderError, match="连接被重置"):
            provider.call("director", {}, Toy, endpoint / "a")


def test_schema_refs_are_inlined_for_gateways_that_reject_defs():
    from movelyth.models import strict_schema

    schema = inline_refs(strict_schema(Toy))
    assert "$defs" not in json.dumps(schema)
    assert "$ref" not in json.dumps(schema)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"title", "items"}


def test_probe_reports_json_and_vision_capability(endpoint):
    from PIL import Image

    sheet = endpoint / "probe.png"
    Image.new("RGB", (32, 32), "red").save(sheet)
    with FakeEndpoint([completion('{"ok": true}'),
                       completion("这张图是红色的。")]) as fake:
        result = probe_endpoint(fake.url, "MOVELYTH_TEST_KEY", "fake-1", image=sheet)
        assert result["reachable"] and result["json_output"] and result["vision"]
        assert "红" in result["vision_answer"]
    with FakeEndpoint([(400, {"error": {"message": "no vision"}}),
                       (400, {"error": {"message": "no vision"}})]) as fake:
        result = probe_endpoint(fake.url, "MOVELYTH_TEST_KEY", "fake-1")
        assert result["reachable"] is False and "no vision" in result["reason"]

import os

import pytest

from movelyth.agents import CodexAgents
from movelyth.models import Review


def test_interrupted_role_stops_owned_process_tree_and_preserves_prior_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr("movelyth.agents.shutil.which", lambda name: "codex")
    stopped = []

    class Process:
        pid = 123456
        returncode = None

        def communicate(self, *args, **kwargs):
            raise KeyboardInterrupt

        def wait(self):
            self.returncode = 1

    monkeypatch.setattr("movelyth.agents.subprocess.Popen", lambda *a, **k: Process())
    monkeypatch.setattr("movelyth.agents.subprocess.run", lambda command, **kwargs: stopped.append(command))
    monkeypatch.setattr("movelyth.agents.os.killpg", lambda *args: stopped.append(args), raising=False)
    base = tmp_path / "role"
    base.mkdir()
    old = base / "response.json"
    old.write_text('{"prior":"attempt"}', encoding="utf-8")
    with pytest.raises(KeyboardInterrupt):
        CodexAgents(tmp_path, {}).call("reviewer", {}, Review, base)
    assert old.read_text(encoding="utf-8") == '{"prior":"attempt"}'
    assert len(list((base / "attempts").iterdir())) == 1
    assert stopped
    if os.name == "nt":
        assert str(Process.pid) in stopped[0]

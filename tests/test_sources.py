from email.message import Message

from movelyth.sources import collect_sources


def test_source_evidence_is_cached_and_scripts_are_not_read_as_article(tmp_path, monkeypatch):
    calls = []

    class Response:
        headers = Message()
        headers["Content-Type"] = "text/html; charset=utf-8"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def geturl(self):
            return "https://example.com/article"

        def read(self, limit):
            return ("<html><nav>navigation</nav><script>do not read this script</script><article>"
                    + "The columns of a matrix specify the images of basis vectors. " * 10
                    + "</article></html>").encode()

    def fetch(*args, **kwargs):
        calls.append(1)
        return Response()

    monkeypatch.setattr("movelyth.sources.urlopen", fetch)
    sources = [{"label": "Test", "url": "https://example.com/article", "supports": "basis vector images"}]
    value = collect_sources(sources, tmp_path)
    assert value[0]["status"] == "retrieved" and len(value[0]["content_sha256"]) == 64
    assert "script" not in value[0]["excerpt"] and "navigation" not in value[0]["excerpt"]
    assert collect_sources(sources, tmp_path) == value and len(calls) == 1

from src.tools.render import renderer_environment


def test_renderer_environment_freezes_version_identity(monkeypatch):
    monkeypatch.setattr("src.tools.render.subprocess.check_output", lambda command, **_: "v-test" if command[0] == "node" else "hf-test")
    monkeypatch.setenv("HYPERFRAMES_BROWSER_VERSION", "chrome-test")

    assert renderer_environment() == {
        "hyperframes_version": "hf-test",
        "node_version": "v-test",
        "browser_version": "chrome-test",
    }

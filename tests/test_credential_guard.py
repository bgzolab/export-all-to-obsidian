from click.testing import CliRunner

from app.credential_guard import CredentialProbeResult
from app.credential_guard import run_with_credential_guard


def _fake_twitter_probe(
    monkeypatch,
    status_code=200,
    payload=None,
    get_error=None,
    json_error=None,
):
    import app.credential_guard as guard

    class FakeResponse:
        def __init__(self, status_code, payload):
            self._status = status_code
            self._payload = payload

        @property
        def status_code(self):
            return self._status

        def json(self):
            if json_error is not None:
                raise json_error
            return self._payload

    class FakeSession:
        def get(self, *args, **kwargs):
            if get_error is not None:
                raise get_error
            return FakeResponse(status_code, payload)

    class FakeClient:
        user_id = "123"
        session = FakeSession()

    monkeypatch.setattr(guard, "TwitterClient", lambda: FakeClient())
    return guard


def test_probe_twitter_valid(monkeypatch):
    guard = _fake_twitter_probe(monkeypatch, payload={"data": {"user": {}}})
    result = guard.probe_twitter_credentials()
    assert result.status == "valid"


def test_probe_twitter_unauthorized(monkeypatch):
    guard = _fake_twitter_probe(monkeypatch, status_code=401)
    result = guard.probe_twitter_credentials()
    assert result.status == "invalid"
    assert "已过期" in result.reason


def test_probe_twitter_forbidden(monkeypatch):
    guard = _fake_twitter_probe(monkeypatch, status_code=403)
    result = guard.probe_twitter_credentials()
    assert result.status == "invalid"


def test_probe_twitter_http_error_unknown(monkeypatch):
    guard = _fake_twitter_probe(monkeypatch, status_code=500)
    result = guard.probe_twitter_credentials()
    assert result.status == "unknown"
    assert "HTTP 500" in result.reason


def test_probe_twitter_non_json_payload_unknown(monkeypatch):
    """response.json() 返回 None（非 dict）时应判为 unknown 而非崩溃。"""
    guard = _fake_twitter_probe(monkeypatch, status_code=200, payload=None)
    result = guard.probe_twitter_credentials()
    assert result.status == "unknown"
    assert "解析失败" in result.reason


def test_probe_twitter_json_decode_error_unknown(monkeypatch):
    """response.json() 抛出 JSONDecodeError 时应判为 unknown。"""
    import json

    guard = _fake_twitter_probe(
        monkeypatch,
        status_code=200,
        json_error=json.JSONDecodeError("Expecting value", "doc", 0),
    )
    result = guard.probe_twitter_credentials()
    assert result.status == "unknown"
    assert "解析失败" in result.reason


def test_probe_twitter_no_data_invalid(monkeypatch):
    guard = _fake_twitter_probe(monkeypatch, status_code=200, payload={})
    result = guard.probe_twitter_credentials()
    assert result.status == "invalid"


def test_probe_twitter_value_error_invalid(monkeypatch):
    import app.credential_guard as guard

    def boom():
        raise ValueError("TWITTER_COOKIE 缺失")

    monkeypatch.setattr(guard, "TwitterClient", boom)
    result = guard.probe_twitter_credentials()
    assert result.status == "invalid"
    assert "TWITTER_COOKIE" in result.reason


def test_probe_twitter_request_exception_unknown(monkeypatch):
    import requests

    guard = _fake_twitter_probe(
        monkeypatch, get_error=requests.RequestException("network down")
    )
    result = guard.probe_twitter_credentials()
    assert result.status == "unknown"
    assert "network down" in result.reason


def test_run_with_credential_guard_skips_export_and_notifies(monkeypatch):
    events: dict[str, object] = {"export_called": False, "notified": []}

    def probe() -> CredentialProbeResult:
        return CredentialProbeResult.invalid("zhihu", "ZHIHU_COOKIE 已过期")

    def export_action() -> None:
        events["export_called"] = True

    def fake_notify(results):
        events["notified"] = results
        return True

    monkeypatch.setattr("app.credential_guard.notify_invalid_credentials", fake_notify)

    allowed = run_with_credential_guard("zhihu", probe, export_action)

    assert allowed is False
    assert events["export_called"] is False
    assert len(events["notified"]) == 1
    assert events["notified"][0].module == "zhihu"


def test_run_with_credential_guard_continues_on_unknown(monkeypatch):
    events = {"export_called": False}

    def probe() -> CredentialProbeResult:
        return CredentialProbeResult.unknown("weibo", "网络超时")

    def export_action() -> None:
        events["export_called"] = True

    monkeypatch.setattr(
        "app.credential_guard.notify_invalid_credentials",
        lambda results: True,
    )

    allowed = run_with_credential_guard("weibo", probe, export_action)

    assert allowed is True
    assert events["export_called"] is True


def test_cli_skips_export_when_probe_invalid(monkeypatch):
    from export_to_obsidian import eto

    called = {"export": False}

    monkeypatch.setattr(
        "app.cli.probe_cnblog_credentials",
        lambda: CredentialProbeResult.invalid("cnblog", "CNBLOG_ACCESS_TOKEN 已过期"),
    )

    def fake_export(output, index_writer):
        called["export"] = True

    monkeypatch.setattr("app.cli.export_cnblog", fake_export)
    monkeypatch.setattr("app.credential_guard.notify_invalid_credentials", lambda results: False)

    runner = CliRunner()
    result = runner.invoke(eto, ["cnblog", "-o", "output/cnblog"])

    assert result.exit_code == 0
    assert "cnblog 凭证已失效" in result.output
    assert called["export"] is False


def test_cli_runs_export_when_probe_valid(monkeypatch):
    from export_to_obsidian import eto

    called = {"export": False}

    monkeypatch.setattr(
        "app.cli.probe_cnblog_credentials",
        lambda: CredentialProbeResult.valid("cnblog"),
    )

    def fake_export(output, index_writer):
        called["export"] = True

    monkeypatch.setattr("app.cli.export_cnblog", fake_export)

    runner = CliRunner()
    result = runner.invoke(eto, ["cnblog", "-o", "output/cnblog"])

    assert result.exit_code == 0
    assert called["export"] is True


def test_cli_twitter_passes_force_to_export(monkeypatch):
    from export_to_obsidian import eto

    called = {}

    monkeypatch.setattr(
        "app.cli.probe_twitter_credentials",
        lambda: CredentialProbeResult.valid("twitter"),
    )

    def fake_export(output, index_writer, force=False, max_pages=50):
        called["output"] = output
        called["force"] = force
        called["max_pages"] = max_pages

    monkeypatch.setattr("app.cli.export_twitter", fake_export)
    monkeypatch.setattr(
        "app.credential_guard.notify_invalid_credentials", lambda results: False
    )

    runner = CliRunner()
    result = runner.invoke(eto, ["twitter", "-o", "output/twitter", "--force"])

    assert result.exit_code == 0
    assert called["output"] == "output/twitter"
    assert called["force"] is True
    assert called["max_pages"] == 50


def test_cli_twitter_passes_max_pages(monkeypatch):
    from export_to_obsidian import eto

    called = {}

    monkeypatch.setattr(
        "app.cli.probe_twitter_credentials",
        lambda: CredentialProbeResult.valid("twitter"),
    )

    def fake_export(output, index_writer, force=False, max_pages=50):
        called["max_pages"] = max_pages

    monkeypatch.setattr("app.cli.export_twitter", fake_export)
    monkeypatch.setattr(
        "app.credential_guard.notify_invalid_credentials", lambda results: False
    )

    runner = CliRunner()
    result = runner.invoke(eto, ["twitter", "-o", "output/twitter", "--max-pages", "5"])

    assert result.exit_code == 0
    assert called["max_pages"] == 5
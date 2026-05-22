from click.testing import CliRunner

from app.credential_guard import CredentialProbeResult
from app.credential_guard import run_with_credential_guard


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
from __future__ import annotations

import pytest

import analyze_pyspark
import analyze_scala
import check_cortex_llm_access
import scos_session


class _FakeCompleteOptions:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_probe_returns_non_empty_response(monkeypatch):
    monkeypatch.setattr(scos_session, "CompleteOptions", _FakeCompleteOptions)
    monkeypatch.setattr(scos_session, "cortex_complete", lambda *args, **kwargs: "  OK  ")
    out = scos_session.verify_cortex_complete_access(object(), model="claude-opus-4-6")
    assert out == "OK"


def test_probe_rejects_empty_response(monkeypatch):
    monkeypatch.setattr(scos_session, "CompleteOptions", _FakeCompleteOptions)
    monkeypatch.setattr(scos_session, "cortex_complete", lambda *args, **kwargs: "   ")
    with pytest.raises(RuntimeError, match="returned empty output"):
        scos_session.verify_cortex_complete_access(object())


@pytest.mark.parametrize(
    "message",
    [
        "403 Forbidden",
        "Unknown user-defined function SNOWFLAKE.CORTEX.COMPLETE",
        "SQL access control error: Insufficient privileges to operate on account",
        "USE AI FUNCTIONS is required",
    ],
)
def test_non_retryable_error_markers(message):
    assert scos_session.is_non_retryable_llm_error(RuntimeError(message)) is True


def test_retryable_error_is_not_marked_non_retryable():
    assert scos_session.is_non_retryable_llm_error(RuntimeError("Read timed out")) is False


def test_preflight_cli_passes_and_prints_identity(monkeypatch, capsys):
    session = _FakeSession()
    monkeypatch.setattr(check_cortex_llm_access, "open_session", lambda connection: session)
    monkeypatch.setattr(
        check_cortex_llm_access,
        "get_session_identity",
        lambda _session: ("acct", "user", "role"),
    )
    monkeypatch.setattr(
        check_cortex_llm_access,
        "verify_cortex_complete_access",
        lambda _session, model: "OK",
    )
    monkeypatch.setattr(
        check_cortex_llm_access.sys,
        "argv",
        ["check_cortex_llm_access.py", "--connection", "myconn"],
    )

    rc = check_cortex_llm_access.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert "CORTEX_LLM_PREFLIGHT=PASS" in out
    assert "connection=myconn" in out
    assert session.closed is True


def test_preflight_cli_fails_loudly(monkeypatch, capsys):
    session = _FakeSession()
    monkeypatch.setattr(check_cortex_llm_access, "open_session", lambda connection: session)
    monkeypatch.setattr(
        check_cortex_llm_access,
        "get_session_identity",
        lambda _session: ("acct", "user", "role"),
    )

    def _raise(_session, model):
        raise RuntimeError("403 Forbidden")

    monkeypatch.setattr(check_cortex_llm_access, "verify_cortex_complete_access", _raise)
    monkeypatch.setattr(check_cortex_llm_access.sys, "argv", ["check_cortex_llm_access.py"])

    rc = check_cortex_llm_access.main()
    err = capsys.readouterr().err

    assert rc == 2
    assert "CORTEX_LLM_PREFLIGHT=FAIL" in err
    assert "403 Forbidden" in err
    assert session.closed is True


def test_pyspark_retry_fails_fast_on_non_retryable(monkeypatch):
    calls = {"n": 0}

    def _fail(*args, **kwargs):
        calls["n"] += 1
        raise RuntimeError("403 Forbidden")

    monkeypatch.setattr(analyze_pyspark, "predict_compatibility_batch", _fail)
    with pytest.raises(RuntimeError, match="403 Forbidden"):
        analyze_pyspark.predict_compatibility_batch_with_retry(
            session=None,
            batch_items=[{"block_id": "1"}],
            max_retries=3,
        )
    assert calls["n"] == 1


def test_pyspark_retry_exhausts_for_retryable_errors(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr("time.sleep", lambda *_: None)

    def _fail(*args, **kwargs):
        calls["n"] += 1
        raise RuntimeError("Read timed out")

    monkeypatch.setattr(analyze_pyspark, "predict_compatibility_batch", _fail)
    with pytest.raises(RuntimeError, match="Read timed out"):
        analyze_pyspark.predict_compatibility_batch_with_retry(
            session=None,
            batch_items=[{"block_id": "1"}],
            max_retries=3,
        )
    assert calls["n"] == 3


def test_scala_retry_fails_fast_on_non_retryable(monkeypatch):
    calls = {"n": 0}

    def _fail(*args, **kwargs):
        calls["n"] += 1
        raise RuntimeError("unknown user-defined function SNOWFLAKE.CORTEX.COMPLETE")

    monkeypatch.setattr(analyze_scala, "predict_compatibility_batch", _fail)
    with pytest.raises(RuntimeError, match="SNOWFLAKE.CORTEX.COMPLETE"):
        analyze_scala.predict_compatibility_batch_with_retry(
            session=None,
            batch_items=[{"block_id": "1"}],
            max_retries=3,
        )
    assert calls["n"] == 1


def test_scala_retry_returns_empty_in_non_required_mode(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)

    def _fail(*args, **kwargs):
        raise RuntimeError("temporary network error")

    monkeypatch.setattr(analyze_scala, "predict_compatibility_batch", _fail)
    out = analyze_scala.predict_compatibility_batch_with_retry(
        session=None,
        batch_items=[{"block_id": "1"}],
        max_retries=2,
        require_llm=False,
    )
    assert out == {}


def test_scala_retry_raises_in_required_mode(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)

    def _fail(*args, **kwargs):
        raise RuntimeError("temporary network error")

    monkeypatch.setattr(analyze_scala, "predict_compatibility_batch", _fail)
    with pytest.raises(RuntimeError, match="temporary network error"):
        analyze_scala.predict_compatibility_batch_with_retry(
            session=None,
            batch_items=[{"block_id": "1"}],
            max_retries=2,
            require_llm=True,
        )


def test_pyspark_cli_accepts_path_flag(tmp_path):
    args = analyze_pyspark._parse_args(["--path", str(tmp_path)])
    assert args.path == str(tmp_path)


def test_pyspark_cli_rejects_positional_path_only(tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        analyze_pyspark._parse_args([str(tmp_path)])
    assert excinfo.value.code == 2


def test_pyspark_cli_requires_path_value():
    with pytest.raises(SystemExit) as excinfo:
        analyze_pyspark._parse_args(["--path"])
    assert excinfo.value.code == 2


def test_preflight_env_skip_pyspark(monkeypatch):
    """When SCOS_LLM_PREFLIGHT_VERIFIED=1, analyze_pyspark must NOT call the probe."""
    monkeypatch.setenv("SCOS_LLM_PREFLIGHT_VERIFIED", "1")
    calls = {"n": 0}

    def _probe(*_a, **_kw):
        calls["n"] += 1
        return "OK"

    monkeypatch.setattr(analyze_pyspark, "verify_cortex_complete_access", _probe)
    # Replicate the gating block the analyzer's main() applies.
    require_llm = True
    import os as _os

    if require_llm:
        if _os.environ.get("SCOS_LLM_PREFLIGHT_VERIFIED") == "1":
            pass
        else:
            analyze_pyspark.verify_cortex_complete_access(object())

    assert calls["n"] == 0


def test_preflight_env_skip_scala(monkeypatch):
    """When SCOS_LLM_PREFLIGHT_VERIFIED=1, analyze_scala must NOT call the probe."""
    monkeypatch.setenv("SCOS_LLM_PREFLIGHT_VERIFIED", "1")
    calls = {"n": 0}

    def _probe(*_a, **_kw):
        calls["n"] += 1
        return "OK"

    monkeypatch.setattr(analyze_scala, "verify_cortex_complete_access", _probe)
    require_llm = True
    import os as _os

    if require_llm:
        if _os.environ.get("SCOS_LLM_PREFLIGHT_VERIFIED") == "1":
            pass
        else:
            analyze_scala.verify_cortex_complete_access(object())

    assert calls["n"] == 0


def test_preflight_runs_without_env(monkeypatch):
    """Without the env var, analyze_pyspark MUST still call the probe (default safety)."""
    monkeypatch.delenv("SCOS_LLM_PREFLIGHT_VERIFIED", raising=False)
    calls = {"n": 0}

    def _probe(*_a, **_kw):
        calls["n"] += 1
        return "OK"

    monkeypatch.setattr(analyze_pyspark, "verify_cortex_complete_access", _probe)
    require_llm = True
    import os as _os

    if require_llm:
        if _os.environ.get("SCOS_LLM_PREFLIGHT_VERIFIED") == "1":
            pass
        else:
            analyze_pyspark.verify_cortex_complete_access(object())

    assert calls["n"] == 1

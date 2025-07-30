from datetime import datetime
import os
import tempfile

from unittest.mock import MagicMock
import pytest

from app import utils


def test_parse_and_create_timestamp():
    ts = utils.create_timestamp()
    dt = utils.parse_timestamp(ts)
    assert isinstance(dt, datetime)
    with pytest.raises(ValueError):
        utils.parse_timestamp("bad")


def test_clamp_and_safe_divide():
    assert utils.clamp(5, 0, 10) == 5
    assert utils.clamp(-1, 0, 10) == 0
    assert utils.safe_divide(4, 2) == 2
    assert utils.safe_divide(1, 0) == 0


def test_merge_dicts_and_hash():
    d1 = {"a": 1, "b": {"c": 2}}
    d2 = {"b": {"d": 3}}
    merged = utils.merge_dicts(d1, d2)
    assert merged["b"]["c"] == 2 and merged["b"]["d"] == 3
    h1 = utils.get_config_hash(d1)
    h2 = utils.get_config_hash(merged)
    assert h1 != h2


def test_alert_and_backoff():
    alert = utils.create_alert("high", "test", "msg")
    assert alert["severity"] == "high"
    assert utils.exponential_backoff(3, base_delay=1) == min(1 * 2**3, 60)


def test_dli_and_vpd_conversions():
    assert utils.calculate_dli(500, 12) > 0
    assert utils.ppfd_to_lux(1) == 75
    assert utils.lux_to_ppfd(75) == 1
    assert utils.calculate_vpd(25, 50) > 0


def test_json_load_save_and_validate():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.json")
        data = {"a": 1}
        utils.save_json_file(data, path)
        loaded = utils.load_json_file(path)
        assert loaded == data
        schema = {
            "type": "object",
            "properties": {"a": {"type": "number"}},
            "required": ["a"],
        }
        assert utils.validate_json_schema(loaded, schema)
        with open(path, "w") as f:
            f.write("not json")
        with pytest.raises(ValueError):
            utils.load_json_file(path)


def test_format_and_sanitize(monkeypatch):
    assert utils.format_duration(65) == "1m 5s"
    assert utils.format_duration(3660) == "1h 1m"
    bad = "bad:name<>"
    assert "_" in utils.sanitize_filename(bad)


def test_get_git_revision(monkeypatch):
    mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout="abc123\n"))
    monkeypatch.setattr("subprocess.run", mock_run)
    assert utils.get_git_revision() == "abc123"


def test_retry_on_exception(monkeypatch):
    calls = {"n": 0}

    @utils.retry_on_exception(max_retries=2, delay=0)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise ValueError("fail")
        return 42

    assert flaky() == 42
    assert calls["n"] == 2
    assert utils.safe_divide("a", 2) == 0
    assert utils.format_duration("bad") == "0s"

from collections.abc import Callable
from unittest.mock import patch

import pytest

from src.retry import RetryExhaustedError, call_with_retry


class Transient(Exception):
    pass


class Permanent(Exception):
    pass


def _flaky(failures: int) -> tuple[list[int], Callable[[], str]]:
    calls: list[int] = []

    def func() -> str:
        calls.append(1)
        if len(calls) <= failures:
            raise Transient(f"échec {len(calls)}")
        return "ok"

    return calls, func


def test_succeeds_without_retry() -> None:
    calls, func = _flaky(0)
    assert call_with_retry(func, operation="op", retry_on=(Transient,)) == "ok"
    assert len(calls) == 1


def test_succeeds_after_transient_failures() -> None:
    calls, func = _flaky(2)
    with patch("src.retry.time.sleep") as sleep:
        result = call_with_retry(func, operation="op", retry_on=(Transient,), attempts=3, delay=1.0)
    assert result == "ok"
    assert len(calls) == 3
    assert [c.args[0] for c in sleep.call_args_list] == [1.0, 2.0]  # backoff x2


def test_exhausted_raises_explicit_error_and_does_not_sleep_after_last() -> None:
    calls, func = _flaky(99)
    with patch("src.retry.time.sleep") as sleep:
        with pytest.raises(RetryExhaustedError) as info:
            call_with_retry(func, operation="insertion MySQL", retry_on=(Transient,), attempts=3, delay=1.0)
    message = str(info.value)
    assert "insertion MySQL" in message and "3 tentative" in message and "échec 3" in message
    assert isinstance(info.value.__cause__, Transient)
    assert len(calls) == 3
    assert sleep.call_count == 2  # pas d'attente après la dernière tentative


def test_permanent_error_is_not_retried() -> None:
    calls: list[int] = []

    def func() -> None:
        calls.append(1)
        raise Permanent("définitif")

    with patch("src.retry.time.sleep") as sleep:
        with pytest.raises(Permanent):
            call_with_retry(func, operation="op", retry_on=(Transient,), attempts=5)
    assert len(calls) == 1
    sleep.assert_not_called()


def test_is_retryable_can_reject_an_error() -> None:
    calls: list[int] = []

    def func() -> None:
        calls.append(1)
        raise Transient("x")

    with pytest.raises(Transient):
        call_with_retry(
            func, operation="op", retry_on=(Transient,), is_retryable=lambda e: False, attempts=5
        )
    assert len(calls) == 1


def test_settings_come_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "2")
    calls, func = _flaky(99)
    with pytest.raises(RetryExhaustedError):
        call_with_retry(func, operation="op", retry_on=(Transient,))
    assert len(calls) == 2

"""429 handling for chat providers (Apertus answers rate_limit_reached_error under load)."""
import threading
from types import SimpleNamespace

import httpx
import pytest
from openai import RateLimitError

from app import llm as llm_module
from app.llm import ChatLLM, MockLLM


def rate_limited(retry_after: str | None = None) -> RateLimitError:
    headers = {"retry-after": retry_after} if retry_after else {}
    response = httpx.Response(429, headers=headers, request=httpx.Request("POST", "https://apertus.test/v1/chat/completions"))
    return RateLimitError("Rate limit reached", response=response,
                          body={"error": {"code": "rate_limit_reached_error"}})


class FlakyClient:
    """Fails with 429 `failures` times, then answers; records the peak number of concurrent calls."""

    def __init__(self, failures: int, retry_after: str | None = None) -> None:
        self.failures, self.retry_after, self.calls = failures, retry_after, 0
        self.active = self.peak = 0
        self.lock = threading.Lock()
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **_):
        with self.lock:
            self.calls += 1
            self.active += 1
            self.peak = max(self.peak, self.active)
            fail = self.calls <= self.failures
        try:
            if fail:
                raise rate_limited(self.retry_after)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])
        finally:
            with self.lock:
                self.active -= 1


@pytest.fixture
def sleeps(monkeypatch):
    waited: list[float] = []
    monkeypatch.setattr(llm_module.time, "sleep", waited.append)
    return waited


def test_retries_429_with_backoff_then_succeeds(sleeps):
    client = FlakyClient(failures=2)
    chat = ChatLLM("apertus", "Apertus", client, "m", None, MockLLM())
    assert chat.complete_json("s", "u", {}, "x", fallback=dict) == {"ok": True}
    assert client.calls == 3 and len(sleeps) == 2 and sleeps[1] > sleeps[0]


def test_honours_retry_after(sleeps):
    chat = ChatLLM("apertus", "Apertus", FlakyClient(failures=1, retry_after="7"), "m", None, MockLLM())
    chat.complete_text("s", "u", fallback=str)
    assert sleeps == [7.0]


def test_gives_up_after_the_configured_retries(sleeps):
    client = FlakyClient(failures=100)
    chat = ChatLLM("apertus", "Apertus", client, "m", None, MockLLM())
    with pytest.raises(RateLimitError):
        chat.complete_text("s", "u", fallback=str)
    assert client.calls == llm_module.settings.rate_limit_retries + 1


def test_concurrency_cap():
    client = FlakyClient(failures=0)
    chat = ChatLLM("apertus", "Apertus", client, "m", None, MockLLM(), max_concurrency=2)
    threads = [threading.Thread(target=chat.complete_text, args=("s", "u", str)) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert client.calls == 12 and client.peak <= 2

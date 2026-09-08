"""One OpenRouter client, shared by judge.py and pitch.py.

Lived inside judge.py first; pitch.py needed the same fallback list, 429
backoff and stray-prose tolerance, so it moved here rather than being copied.

OpenRouter is OpenAI-compatible. Primary + fallbacks: if one free pool is
rate-limited upstream, OpenRouter routes to the next automatically.
"""
import json, os, sys, time
import requests

class TransientLLMError(RuntimeError):
    """A failure worth retrying: provider hiccup, empty pool, network blip."""


URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS = [  # OpenRouter caps the fallback array at 3
    "nvidia/nemotron-3-super-120b-a12b:free",
    "minimax/minimax-m3:free",
    "z-ai/glm-5.2:free",
]
PACE = 4        # seconds between calls; free tier is ~20 req/min
RETRIES = 4
BACKOFF = 6     # seconds, multiplied by the attempt number


def key():
    k = os.environ.get("OPENROUTER_API_KEY")
    if not k:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    return k


def _extract(text):
    """Tolerate a model that wraps its JSON in prose or a fence."""
    if not text:
        # A model can return null content (empty completion, or a refusal
        # expressed as tool_calls). Observed once in 68 calls.
        raise ValueError("model returned empty content")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"no JSON object in response: {text[:120]!r}")
    return json.loads(text[start:end + 1])


def _content(payload):
    """Pull the completion text out of an OpenRouter response.

    OpenRouter answers HTTP 200 with {"error": {...}} and no `choices` when a
    free pool fails upstream: 7 of 68 calls in one run died on a bare KeyError
    that said only 'choices'. Surfacing the real message makes it retryable.
    """
    if "error" in payload and not payload.get("choices"):
        err = payload["error"]
        msg = err.get("message") if isinstance(err, dict) else err
        raise TransientLLMError(f"provider error: {msg}")
    choices = payload.get("choices")
    if not choices:
        raise TransientLLMError(f"no choices in response: {str(payload)[:160]}")
    return choices[0].get("message", {}).get("content")


def ask_json(prompt, api_key=None, json_mode=True, temperature=0):
    """One call, returns the parsed JSON object.

    Retries every transient class, not just 429. A long batch on a laptop or a
    CI runner will hit connection resets, read timeouts and DNS blips; in one
    68-call run those cost 17 results purely because requests.post was outside
    the retry loop.
    """
    body = {"models": MODELS, "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}]}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {api_key or key()}",
               "Content-Type": "application/json"}

    last = None
    for attempt in range(RETRIES):
        try:
            r = requests.post(URL, headers=headers, json=body, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                last = TransientLLMError(f"HTTP {r.status_code}")
            else:
                r.raise_for_status()
                return _extract(_content(r.json()))
        except (requests.RequestException, TransientLLMError, ValueError) as e:
            last = e
        if attempt < RETRIES - 1:
            time.sleep(BACKOFF * (attempt + 1))
    raise TransientLLMError(f"{RETRIES} attempts failed, last: {last}")


def _selfcheck():
    assert _extract('{"a": 1}') == {"a": 1}
    assert _extract('sure! ```json\n{"a": [1,2]}\n``` hope that helps') == {"a": [1, 2]}
    assert _extract('prose {"a": {"b": 2}} more') == {"a": {"b": 2}}
    for bad in ["no json here", "", "}{"]:
        try:
            _extract(bad)
            raise AssertionError(f"should have raised on {bad!r}")
        except (ValueError, json.JSONDecodeError):
            pass
    # empty content is an error with a readable message, not an AttributeError
    for empty in [None, ""]:
        try:
            _extract(empty)
            raise AssertionError("should have raised")
        except ValueError as e:
            assert "empty content" in str(e)

    # an OpenRouter error body is transient and says why, not just 'choices'
    assert _content({"choices": [{"message": {"content": "hi"}}]}) == "hi"
    assert _content({"choices": [{"message": {}}]}) is None      # caught by _extract
    for bad in [{"error": {"message": "pool exhausted"}}, {"error": "nope"}, {}]:
        try:
            _content(bad)
            raise AssertionError(f"should have raised on {bad}")
        except TransientLLMError as e:
            assert str(e) and "choices'" != str(e)
    # the message must name the cause, so a log line is actionable
    try:
        _content({"error": {"message": "pool exhausted"}})
    except TransientLLMError as e:
        assert "pool exhausted" in str(e)

    assert len(MODELS) <= 3, "OpenRouter caps the fallback array at 3"
    print("llm selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()

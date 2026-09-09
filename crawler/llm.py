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


class RateLimitError(TransientLLMError):
    """Every retry died on HTTP 429. On free models this means the daily quota
    is spent, not a passing blip: no pace fixes a daily cap, so the caller
    should stop the batch rather than 429 its way through the rest."""


URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS = [  # OpenRouter caps the fallback array at 3. All 3 verified live on
            # OpenRouter and support response_format=json_object (checked via
            # /api/v1/models). Gemma leads because it writes the most natural
            # openers; nemotron-super is the heavier fallback for classification.
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-26b-a4b-it:free",
]
PACE = 4        # seconds between calls; free tier is ~20 req/min
RETRIES = 4
BACKOFF = 6     # seconds, multiplied by the attempt number


def all_keys():
    """Every OpenRouter key, in priority order: OPENROUTER_API_KEY, then
    OPENROUTER_API_KEY_2, _3, ... ask_json rotates to the next key when the
    current one's free quota is spent (all-429), so a second key doubles the
    daily budget. Set each as its own GitHub secret; never commit the value."""
    keys, i = [], 1
    while True:
        name = "OPENROUTER_API_KEY" if i == 1 else f"OPENROUTER_API_KEY_{i}"
        v = os.environ.get(name)
        if v and v.strip():
            keys.append(v.strip())
        elif i > 1:
            break        # stop at the first missing _N slot (keys are contiguous)
        i += 1
        if i > 10:
            break
    if not keys:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    return keys


def key():
    """First key only. Kept for callers that want a single explicit key."""
    return all_keys()[0]


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


def _ask_once(prompt, api_key, json_mode, temperature):
    """One key, up to RETRIES attempts. Returns the parsed JSON, or raises
    RateLimitError if EVERY attempt was 429 (this key's quota is spent) or
    TransientLLMError for any other exhausted-retry failure.

    Retries every transient class, not just 429. A long batch on a laptop or a
    CI runner will hit connection resets, read timeouts and DNS blips; in one
    68-call run those cost 17 results purely because requests.post was outside
    the retry loop.
    """
    body = {"models": MODELS, "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}]}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {api_key}",
               "Content-Type": "application/json"}

    last = None
    all_429 = True
    for attempt in range(RETRIES):
        try:
            r = requests.post(URL, headers=headers, json=body, timeout=60)
            if r.status_code == 429:
                last = TransientLLMError("HTTP 429")
            elif r.status_code >= 500:
                last, all_429 = TransientLLMError(f"HTTP {r.status_code}"), False
            else:
                r.raise_for_status()
                return _extract(_content(r.json()))
        except (requests.RequestException, TransientLLMError, ValueError) as e:
            if not (isinstance(e, TransientLLMError) and str(e) == "HTTP 429"):
                all_429 = False
            last = e
        if attempt < RETRIES - 1:
            time.sleep(BACKOFF * (attempt + 1))
    if all_429:
        raise RateLimitError(f"{RETRIES} attempts all 429 (free-model quota spent?)")
    raise TransientLLMError(f"{RETRIES} attempts failed, last: {last}")


# Keys whose daily quota is spent for THIS process. A run is one process, so a
# key that 429s its way out once should not be retried (4 attempts x backoff
# ~36s) on every later batch - that was the "stuck" symptom. Reset naturally
# next cron, which is a fresh process by which time the quota has rolled over.
_spent = set()


def ask_json(prompt, api_key=None, json_mode=True, temperature=0):
    """One call, returns the parsed JSON object. Rotates through every
    configured key, skipping any already known spent this run: when a key's
    quota is spent (all-429) it is remembered and the next key is tried.
    RateLimitError only escapes once EVERY key is exhausted, so the batch's
    circuit breaker stops the run only when there is genuinely no budget left."""
    keys = [api_key] if api_key else all_keys()
    live = [k for k in keys if k not in _spent]
    if not live:
        raise RateLimitError("all keys quota-exhausted this run")
    last = None
    for i, k in enumerate(live):
        try:
            return _ask_once(prompt, k, json_mode, temperature)
        except RateLimitError as e:
            last = e
            _spent.add(k)   # skip this key for the rest of the run
            if i + 1 < len(live):
                print(f"  a key's quota is spent, switching to the next "
                      f"({len(live) - i - 1} left)", file=sys.stderr)
    raise last  # all keys 429 -> real quota wall, let the caller stop the batch


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

    # RateLimitError is a TransientLLMError so existing handlers still catch it,
    # but callers can single it out to stop a batch when the quota is spent.
    assert issubclass(RateLimitError, TransientLLMError)
    assert len(MODELS) <= 3, "OpenRouter caps the fallback array at 3"
    print("llm selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()

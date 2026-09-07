"""One OpenRouter client, shared by judge.py and pitch.py.

Lived inside judge.py first; pitch.py needed the same fallback list, 429
backoff and stray-prose tolerance, so it moved here rather than being copied.

OpenRouter is OpenAI-compatible. Primary + fallbacks: if one free pool is
rate-limited upstream, OpenRouter routes to the next automatically.
"""
import json, os, sys, time
import requests

URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS = [  # OpenRouter caps the fallback array at 3
    "nvidia/nemotron-3-super-120b-a12b:free",
    "minimax/minimax-m3:free",
    "z-ai/glm-5.2:free",
]
PACE = 4        # seconds between calls; free tier is ~20 req/min
RETRIES = 4


def key():
    k = os.environ.get("OPENROUTER_API_KEY")
    if not k:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    return k


def _extract(text):
    """Tolerate a model that wraps its JSON in prose or a fence."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"no JSON object in response: {text[:120]!r}")
    return json.loads(text[start:end + 1])


def ask_json(prompt, api_key=None, json_mode=True, temperature=0):
    """One call, returns the parsed JSON object. Raises on exhausted retries."""
    body = {"models": MODELS, "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}]}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {api_key or key()}",
               "Content-Type": "application/json"}
    r = None
    for attempt in range(RETRIES):
        r = requests.post(URL, headers=headers, json=body, timeout=60)
        if r.status_code == 429:      # all free pools busy -> back off and retry
            time.sleep(6 * (attempt + 1))
            continue
        r.raise_for_status()
        return _extract(r.json()["choices"][0]["message"]["content"])
    r.raise_for_status()              # exhausted retries


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
    assert len(MODELS) <= 3, "OpenRouter caps the fallback array at 3"
    print("llm selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()

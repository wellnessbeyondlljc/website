"""
Navigator adapter smoke test.

For every adapter where is_available() is True, sends a single minimal
prompt and asserts the return dict contains the required keys.

Run from framework root:
    python3 tools/navigator_smoke.py
"""

import inspect
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ADAPTERS_DIR = Path(__file__).resolve().parents[1] / "hub" / "WAI-Hub" / "advisors" / "navigator" / "adapters"

REQUIRED_RETURN_KEYS = {"text", "tokens_in", "tokens_out", "latency_ms", "raw"}

# Cheapest/fastest model per provider for smoke-test purposes
SMOKE_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash-lite",
    "together": "meta-llama/Llama-3-8b-chat-hf",
    "z_ai": "glm-4-flash",
    "nvidia": "meta/llama-3.1-8b-instruct",
}

PROBE_MESSAGES = [{"role": "user", "content": "Reply OK"}]

ADAPTER_NAMES = ["anthropic", "openai", "gemini", "together", "z_ai", "nvidia"]


def load_adapter(name: str):
    path = ADAPTERS_DIR / f"{name}.py"
    if not path.exists():
        raise FileNotFoundError(f"Adapter not found: {path}")
    spec = spec_from_file_location(name, path)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_signature(mod) -> bool:
    """Verify chat_completion(model, messages, **kwargs) signature."""
    fn = getattr(mod, "chat_completion", None)
    if fn is None:
        return False
    sig = inspect.signature(fn)
    params = list(sig.parameters.keys())
    return "model" in params and "messages" in params


def run(name: str) -> str:
    try:
        mod = load_adapter(name)
    except Exception as exc:
        return f"LOAD_ERROR: {exc}"

    if not check_signature(mod):
        return "FAIL: chat_completion missing or wrong signature"

    if not mod.is_available():
        return "SKIP (env key not set)"

    model = SMOKE_MODELS.get(name)
    if model is None:
        return "SKIP (no smoke model configured)"

    try:
        result = mod.chat_completion(model, PROBE_MESSAGES, max_tokens=16)
    except Exception as exc:
        return f"FAIL: {exc}"

    missing = REQUIRED_RETURN_KEYS - set(result.keys())
    if missing:
        return f"FAIL: missing return keys {missing}"

    if not isinstance(result.get("text"), str):
        return "FAIL: 'text' is not a str"

    return "PASS"


def main():
    any_fail = False
    for name in ADAPTER_NAMES:
        status = run(name)
        print(f"  {name:12s}  {status}")
        if status.startswith("FAIL"):
            any_fail = True

    if any_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()

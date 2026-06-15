"""
Tests for DeepSeek API integration:
  1. deepseek_dispatch.py output format (mocked HTTP)
  2. OziAutopilot --provider deepseek tier-map wiring (no API calls)
  3. Navigator adapter contract (mocked HTTP)
  4. Live integration quality checks (skipped unless DEEPSEEK_API_KEY set)
"""

import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
HUB_TOOLS = REPO_ROOT / "hub" / "tools"
ADAPTER_DIR = REPO_ROOT / "hub" / "WAI-Hub" / "advisors" / "navigator" / "adapters"
TOOLS_DIR = REPO_ROOT / "tools"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Fake HTTP response helper
# ---------------------------------------------------------------------------
_FAKE_DEEPSEEK_RESPONSE = {
    "id": "chatcmpl-test",
    "choices": [{"message": {"role": "assistant", "content": "OK"}}],
    "usage": {
        "prompt_tokens": 42,
        "completion_tokens": 7,
        "total_tokens": 49,
    },
}


class _FakeHTTPResp:
    def __init__(self, payload: dict):
        self._data = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# Group 1 — deepseek_dispatch.py output format
# ---------------------------------------------------------------------------
class TestDeepseekDispatchOutputFormat(unittest.TestCase):
    def _run_dispatch(self, model: str = "deepseek-chat", prompt: str = "Reply with OK") -> dict:
        dispatch_path = HUB_TOOLS / "deepseek_dispatch.py"
        mod = _load_module(dispatch_path, "deepseek_dispatch")

        fake_resp = _FakeHTTPResp(_FAKE_DEEPSEEK_RESPONSE)
        captured = io.StringIO()

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}), \
             patch("urllib.request.urlopen", return_value=fake_resp), \
             patch("sys.stdin", io.StringIO(prompt)), \
             patch("sys.stdout", captured), \
             patch("sys.argv", ["deepseek_dispatch.py", "--model", model]):
            mod.main()

        output = captured.getvalue().strip()
        return json.loads(output)

    def test_usage_fields_present(self):
        out = self._run_dispatch()
        self.assertIn("usage", out)
        usage = out["usage"]
        self.assertIn("input_tokens", usage)
        self.assertIn("output_tokens", usage)

    def test_prompt_tokens_mapped_to_input_tokens(self):
        out = self._run_dispatch()
        # DeepSeek returns prompt_tokens=42; dispatch must map → input_tokens=42
        self.assertEqual(out["usage"]["input_tokens"], 42)

    def test_completion_tokens_mapped_to_output_tokens(self):
        out = self._run_dispatch()
        self.assertEqual(out["usage"]["output_tokens"], 7)

    def test_content_field_present(self):
        out = self._run_dispatch()
        self.assertEqual(out["content"], "OK")

    def test_model_field_present(self):
        out = self._run_dispatch(model="deepseek-chat")
        self.assertEqual(out["model"], "deepseek-chat")

    def test_exit_1_without_api_key(self):
        dispatch_path = HUB_TOOLS / "deepseek_dispatch.py"
        mod = _load_module(dispatch_path, "deepseek_dispatch_nokey")

        env_without_key = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
        with self.assertRaises(SystemExit) as cm, \
             patch.dict(os.environ, env_without_key, clear=True), \
             patch("sys.argv", ["deepseek_dispatch.py", "--model", "deepseek-chat"]), \
             patch("sys.stdin", io.StringIO("hello")):
            mod.main()
        self.assertEqual(cm.exception.code, 1)

    def test_exit_1_on_http_error(self):
        import urllib.error
        dispatch_path = HUB_TOOLS / "deepseek_dispatch.py"
        mod = _load_module(dispatch_path, "deepseek_dispatch_httperr")

        http_err = urllib.error.HTTPError(
            url="https://api.deepseek.com/chat/completions",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=io.BytesIO(b"invalid key"),
        )
        with self.assertRaises(SystemExit) as cm, \
             patch.dict(os.environ, {"DEEPSEEK_API_KEY": "bad-key"}), \
             patch("urllib.request.urlopen", side_effect=http_err), \
             patch("sys.argv", ["deepseek_dispatch.py", "--model", "deepseek-chat"]), \
             patch("sys.stdin", io.StringIO("hello")):
            mod.main()
        self.assertEqual(cm.exception.code, 1)


# ---------------------------------------------------------------------------
# Group 2 — OziAutopilot --provider deepseek tier-map wiring
# ---------------------------------------------------------------------------
class TestOziAutopilotDeepseekProviderWiring(unittest.TestCase):
    def _make_minimal_autopilot(self, provider: str, tmp_path: Path):
        """Construct OziAutopilot with minimal filesystem scaffold."""
        # Create WAI-Spoke structure
        wai = tmp_path / "WAI-Spoke"
        wai.mkdir(parents=True)
        state = {
            "schema_version": "2.0",
            "wheel_id": "test-spoke",
            "wheel": {"name": "test", "spoke_id": "test-spoke"},
        }
        (wai / "WAI-State.json").write_text(json.dumps(state))
        (wai / "advisors").mkdir()
        (wai / "advisors" / "navigator").mkdir()

        # Add ozi_autopilot to sys.path
        if str(TOOLS_DIR) not in sys.path:
            sys.path.insert(0, str(TOOLS_DIR))

        from ozi_autopilot import OziAutopilot
        ap = OziAutopilot(
            spoke_path=tmp_path,
            budget=1,
            hub_dir=None,
            dry_run=True,
            token_limit=200_000,
            token_stop_threshold=50_000,
            provider=provider,
        )
        return ap

    def test_deepseek_provider_sets_deepseek_tier_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            ap = self._make_minimal_autopilot("deepseek", Path(tmp))
            # _assess_state populates navigator_profile — call it implicitly via
            # accessing the class constant before run (we verify the map directly)
            self.assertEqual(ap.DEEPSEEK_TIER_MAP["haiku"]["model_id"], "deepseek-chat")
            self.assertEqual(ap.DEEPSEEK_TIER_MAP["sonnet"]["model_id"], "deepseek-chat")
            self.assertEqual(ap.DEEPSEEK_TIER_MAP["opus"]["model_id"], "deepseek-reasoner")

    def test_anthropic_is_default_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            ap = self._make_minimal_autopilot("anthropic", Path(tmp))
            self.assertEqual(ap._provider, "anthropic")

    def test_deepseek_provider_stored(self):
        with tempfile.TemporaryDirectory() as tmp:
            ap = self._make_minimal_autopilot("deepseek", Path(tmp))
            self.assertEqual(ap._provider, "deepseek")

    def test_resolve_provider_cmd_deepseek_chat(self):
        with tempfile.TemporaryDirectory() as tmp:
            ap = self._make_minimal_autopilot("deepseek", Path(tmp))
            dispatch_path = HUB_TOOLS / "deepseek_dispatch.py"
            if dispatch_path.exists():
                cmd = ap._resolve_provider_cmd("deepseek-chat", None)
                self.assertIn("deepseek_dispatch.py", " ".join(cmd))
                self.assertIn("--model", cmd)
                self.assertIn("deepseek-chat", cmd)
            else:
                self.skipTest("deepseek_dispatch.py not found — skipping cmd resolution check")

    def test_resolve_provider_cmd_deepseek_reasoner(self):
        with tempfile.TemporaryDirectory() as tmp:
            ap = self._make_minimal_autopilot("deepseek", Path(tmp))
            dispatch_path = HUB_TOOLS / "deepseek_dispatch.py"
            if dispatch_path.exists():
                cmd = ap._resolve_provider_cmd("deepseek-reasoner", None)
                self.assertIn("deepseek_dispatch.py", " ".join(cmd))
                self.assertIn("deepseek-reasoner", cmd)
            else:
                self.skipTest("deepseek_dispatch.py not found")

    def test_deepseek_tier_map_all_three_tiers_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            ap = self._make_minimal_autopilot("deepseek", Path(tmp))
            for tier in ("haiku", "sonnet", "opus"):
                self.assertIn(tier, ap.DEEPSEEK_TIER_MAP)
                entry = ap.DEEPSEEK_TIER_MAP[tier]
                self.assertIn("model_id", entry)
                self.assertEqual(entry["provider"], "deepseek")


# ---------------------------------------------------------------------------
# Group 3 — Navigator adapter contract (mocked HTTP)
# ---------------------------------------------------------------------------
class TestDeepseekNavigatorAdapter(unittest.TestCase):
    def _load_adapter(self):
        adapter_path = ADAPTER_DIR / "deepseek.py"
        return _load_module(adapter_path, "deepseek_adapter")

    def test_is_available_false_without_key(self):
        mod = self._load_adapter()
        env_without_key = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
        with patch.dict(os.environ, env_without_key, clear=True):
            self.assertFalse(mod.is_available())

    def test_is_available_true_with_key(self):
        mod = self._load_adapter()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
            self.assertTrue(mod.is_available())

    def test_list_models_returns_error_without_key(self):
        mod = self._load_adapter()
        env_without_key = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
        with patch.dict(os.environ, env_without_key, clear=True):
            result = mod.list_models()
        self.assertEqual(result["provider"], "deepseek")
        self.assertIn("error", result)
        self.assertEqual(result["models"], [])

    def test_list_models_fallback_on_api_failure(self):
        mod = self._load_adapter()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}), \
             patch("urllib.request.urlopen", side_effect=Exception("network down")):
            result = mod.list_models()
        self.assertEqual(result["source"], "fallback")
        self.assertGreater(len(result["models"]), 0)

    def test_get_pricing_catalog_keys(self):
        mod = self._load_adapter()
        catalog = mod.get_pricing_catalog()
        self.assertEqual(catalog["provider"], "deepseek")
        self.assertIn("deepseek-chat", catalog["pricing"])
        self.assertIn("deepseek-reasoner", catalog["pricing"])

    def test_chat_completion_normalizes_token_fields(self):
        mod = self._load_adapter()
        fake_resp = _FakeHTTPResp(_FAKE_DEEPSEEK_RESPONSE)
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}), \
             patch("urllib.request.urlopen", return_value=fake_resp):
            result = mod.chat_completion("deepseek-chat", [{"role": "user", "content": "hi"}])
        # Adapter returns tokens_in/tokens_out (Navigator contract)
        self.assertEqual(result["tokens_in"], 42)
        self.assertEqual(result["tokens_out"], 7)
        self.assertEqual(result["text"], "OK")
        self.assertIn("latency_ms", result)
        self.assertIn("raw", result)

    def test_chat_completion_raises_without_key(self):
        mod = self._load_adapter()
        env_without_key = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
        with patch.dict(os.environ, env_without_key, clear=True), \
             self.assertRaises(RuntimeError):
            mod.chat_completion("deepseek-chat", [{"role": "user", "content": "hi"}])

    def test_required_return_keys_present(self):
        mod = self._load_adapter()
        fake_resp = _FakeHTTPResp(_FAKE_DEEPSEEK_RESPONSE)
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}), \
             patch("urllib.request.urlopen", return_value=fake_resp):
            result = mod.chat_completion("deepseek-chat", [{"role": "user", "content": "hi"}])
        required = {"text", "tokens_in", "tokens_out", "latency_ms", "raw"}
        self.assertTrue(required.issubset(result.keys()))


# ---------------------------------------------------------------------------
# Group 4 — Live integration quality checks (require DEEPSEEK_API_KEY)
# ---------------------------------------------------------------------------
_HAS_API_KEY = bool(os.environ.get("DEEPSEEK_API_KEY"))


@unittest.skipUnless(_HAS_API_KEY, "DEEPSEEK_API_KEY not set — skipping live integration tests")
class TestDeepseekLiveIntegration(unittest.TestCase):
    """Live API tests. Run with: DEEPSEEK_API_KEY=<key> python3 -m pytest tests/test_deepseek_integration.py -k live -v"""

    def _load_adapter(self):
        return _load_module(ADAPTER_DIR / "deepseek.py", "deepseek_live")

    def test_deepseek_chat_responds_to_simple_prompt(self):
        mod = self._load_adapter()
        result = mod.chat_completion(
            "deepseek-chat",
            [{"role": "user", "content": "Reply with exactly the word: CONFIRMED"}],
            max_tokens=20,
        )
        self.assertIn("CONFIRMED", result["text"].upper())
        self.assertGreater(result["tokens_in"], 0)
        self.assertGreater(result["tokens_out"], 0)
        print(f"\n[live] deepseek-chat: in={result['tokens_in']} out={result['tokens_out']} "
              f"latency={result['latency_ms']}ms "
              f"cost_est=${result['tokens_in']*0.00000014 + result['tokens_out']*0.00000028:.6f}")

    def test_deepseek_chat_coding_task(self):
        mod = self._load_adapter()
        result = mod.chat_completion(
            "deepseek-chat",
            [{"role": "user", "content": "Write a Python function that returns the sum of a list. One function only, no explanation."}],
            max_tokens=200,
        )
        self.assertIn("def ", result["text"])
        self.assertIn("return", result["text"])
        print(f"\n[live] deepseek-chat coding: out_tokens={result['tokens_out']} latency={result['latency_ms']}ms")

    def test_deepseek_reasoner_responds(self):
        mod = self._load_adapter()
        result = mod.chat_completion(
            "deepseek-reasoner",
            [{"role": "user", "content": "What is 17 * 23? Reply with just the number."}],
            max_tokens=200,
        )
        # R1 may return the answer in content or reasoning_content; the adapter
        # falls back to reasoning_content when content is empty — check both.
        answer_text = (
            result["text"]
            or result["raw"].get("choices", [{}])[0].get("message", {}).get("reasoning_content", "")
        )
        self.assertIn("391", answer_text, f"Expected 391 in response, got: {answer_text[:200]!r}")
        self.assertGreater(result["tokens_out"], 0)
        print(f"\n[live] deepseek-reasoner: in={result['tokens_in']} out={result['tokens_out']} "
              f"latency={result['latency_ms']}ms "
              f"cost_est=${result['tokens_in']*0.00000055 + result['tokens_out']*0.00000219:.6f}")

    def test_dispatch_script_live(self):
        """Smoke test deepseek_dispatch.py as a subprocess."""
        import subprocess
        dispatch_path = HUB_TOOLS / "deepseek_dispatch.py"
        proc = subprocess.run(
            [sys.executable, str(dispatch_path), "--model", "deepseek-chat", "--max-tokens", "20"],
            input="Reply with exactly: DISPATCH_OK",
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "DEEPSEEK_API_KEY": os.environ["DEEPSEEK_API_KEY"]},
        )
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr[:300]}")
        out = json.loads(proc.stdout)
        self.assertIn("usage", out)
        self.assertIn("input_tokens", out["usage"])
        self.assertIn("output_tokens", out["usage"])
        self.assertGreater(out["usage"]["input_tokens"], 0)
        print(f"\n[live] dispatch subprocess: {out['usage']}")


if __name__ == "__main__":
    unittest.main()

"""Run: python3 /home/ubuntu/litellm/test_pl_openai_fallback.py (stubs litellm)."""
import sys, types
m = types.ModuleType("litellm.integrations.custom_logger"); m.CustomLogger = object
sys.modules.update({"litellm": types.ModuleType("litellm"), "litellm.integrations": types.ModuleType("x"),
                    "litellm.integrations.custom_logger": m})
sys.path.insert(0, "/home/ubuntu/litellm")
import asyncio
from pl_openai_fallback import OpenAIFallbackParams, to_openai_params

def test_gemini_no_thinking_call_becomes_valid_openai():
    out = to_openai_params({"model": "openai/gpt-6-luna", "reasoning_effort": "disable", "temperature": 0.3,
                            "max_tokens": 300, "thinking_config": {"thinking_budget": 0},
                            "extra_body": {"thinkingConfig": {}}, "response_format": {"type": "json_schema",
                            "json_schema": {"name": "R", "strict": True, "schema": {}}}})
    assert out["extra_body"]["reasoning_effort"] == "none" and "reasoning_effort" not in out
    assert out["temperature"] == 0.3
    assert out["max_completion_tokens"] == 300 and "max_tokens" not in out
    assert "thinking_config" not in out and out["extra_body"] == {"reasoning_effort": "none"}
    assert out["response_format"]["json_schema"]["strict"] is False

def test_reasoning_call_drops_sampling_and_lifts_cap():
    out = to_openai_params({"reasoning_effort": "low", "temperature": 0.5, "top_p": 0.9, "max_tokens": 500})
    assert out["reasoning_effort"] == "low" and "extra_body" not in out
    assert "temperature" not in out and "top_p" not in out and out["max_completion_tokens"] == 4096

def test_missing_reasoning_means_none():
    assert to_openai_params({})["extra_body"] == {"reasoning_effort": "none"}

def test_only_openai_fallback_models_are_rewritten():
    hook = OpenAIFallbackParams()
    run = lambda model: asyncio.run(hook.async_pre_call_deployment_hook({"model": model, "reasoning_effort": "disable"}, None))
    assert run("gemini/gemini-3-flash-preview") is None and run("openai/gpt-5-mini") is None
    assert run("openai/gpt-5.4-mini")["extra_body"] == {"reasoning_effort": "none"}

for name, fn in list(globals().items()):
    if name.startswith("test_"):
        fn(); print("PASS", name)

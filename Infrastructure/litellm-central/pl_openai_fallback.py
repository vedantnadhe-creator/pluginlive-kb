"""Make Gemini-shaped requests acceptable to the OpenAI fallback models.

Every service calls the gateway with Gemini settings (reasoning_effort
"disable", thinking budgets, max_tokens, strict schemas generated for Gemini).
OpenAI rejects each of those, so a router fallback to OpenAI failed a second
time instead of answering. This rewrites the request just before it is sent to
an OpenAI fallback deployment, so no service needs to know which provider
answers. Legacy Gemini deployments are untouched. Central task calls apply their
provider-specific reasoning policy before every deployment attempt.

Loaded via `litellm_settings.callbacks` in config.yaml and mounted read-only at
/app/pl_openai_fallback.py: DEV/UAT by ~/litellm/run.sh, PROD by the
`litellm-fallback-hook` ConfigMap. Edit it here, then restart the gateway.
"""
import re
import json
import logging
from pathlib import Path

from fastapi import HTTPException

POLICY_PATH = Path(__file__).parent / "policies" / "tasks.json"
logger = logging.getLogger("pluginlive.llm_policy")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())

from litellm.integrations.custom_logger import CustomLogger

OPENAI_FALLBACK_MODEL = re.compile(r"(^|/)gpt-(5\.4-mini|6-luna)$")
GEMINI_ONLY_PARAMS = ("thinking", "thinking_config", "thinkingConfig", "top_k")
GEMINI_NO_THINKING = (None, "disable", "minimal")
# Reasoning shares the completion budget, so a cap sized for a no-thinking Gemini
# call would leave nothing for the answer.
MIN_REASONING_COMPLETION_TOKENS = 4096


def to_openai_params(kwargs: dict) -> dict:
    for name in GEMINI_ONLY_PARAMS:
        kwargs.pop(name, None)
    extra_body = kwargs.get("extra_body")
    if isinstance(extra_body, dict):
        for name in GEMINI_ONLY_PARAMS:
            extra_body.pop(name, None)

    effort = kwargs.get("reasoning_effort")
    if effort in GEMINI_NO_THINKING:
        effort = kwargs["reasoning_effort"] = "none"
    if effort != "none":
        # These models accept only the default sampling once reasoning is on.
        kwargs.pop("temperature", None)
        kwargs.pop("top_p", None)

    if "max_tokens" in kwargs:
        cap = kwargs.pop("max_tokens")
        if effort != "none" and cap is not None:
            cap = max(cap, MIN_REASONING_COMPLETION_TOKENS)
        if cap is not None:
            kwargs["max_completion_tokens"] = cap

    if effort == "none":
        # Sent raw: with a temperature present LiteLLM's gpt-5-family mapping
        # loses a top-level reasoning_effort="none", and OpenAI then rejects the
        # temperature as if reasoning were on.
        kwargs.pop("reasoning_effort")
        kwargs["extra_body"] = {**(kwargs.get("extra_body") or {}), "reasoning_effort": "none"}

    response_format = kwargs.get("response_format")
    if isinstance(response_format, dict) and response_format.get("type") == "json_schema":
        # Schemas are generated for Gemini; OpenAI strict mode rejects most of them
        # (it needs additionalProperties: false and every property required).
        kwargs["response_format"] = {
            **response_format,
            "json_schema": {**response_format.get("json_schema", {}), "strict": False},
        }
    return kwargs


def load_policies():
    """Read the mounted policy on each request; atomic replacement needs no restart."""
    document = json.loads(POLICY_PATH.read_text())
    if document.get("version") != 1 or not isinstance(document.get("tasks"), dict):
        raise ValueError("Invalid LLM policy document")
    return document["tasks"]


def validate_policy(task, policy):
    models = [policy["primary"], *policy["fallbacks"]]
    if not task.startswith("pl/") or not models or len(models) != len(set(models)):
        raise ValueError("Invalid task or duplicate model in policy")
    if any(not isinstance(model, str) or not model for model in models):
        raise ValueError("Invalid model in policy")
    if not 0 < policy["timeout"] <= 300 or not 0 <= policy["retries"] <= 2:
        raise ValueError("Invalid timeout or retry count")
    if policy["modality"] in ("audio", "grounding", "image"):
        if any(not model.startswith("gemini-") for model in models):
            raise ValueError("This task requires a compatible Gemini chain")
    return policy


def route_task(data, policies):
    task = data.get("model", "")
    if not isinstance(task, str) or not task.startswith("pl/"):
        # Compatibility for callers not migrated yet, including PROD clients.
        return data
    if task not in policies:
        raise HTTPException(status_code=400, detail="Unknown centralized LLM task")
    policy = validate_policy(task, policies[task])
    has_audio = any(part.get("type") == "input_audio"
                    for message in data.get("messages", [])
                    if isinstance(message.get("content"), list)
                    for part in message["content"] if isinstance(part, dict))
    if has_audio and policy["modality"] != "audio":
        raise HTTPException(status_code=400, detail="Audio input requires an audio task")
    data["model"] = policy["primary"]
    # An explicit flat chain overrides the global per-model chains, including
    # the global OpenAI fallback of the listener's Gemini 3.8 audio hop.
    data["fallbacks"] = [{"model": model} for model in policy["fallbacks"]]
    data["timeout"] = policy["timeout"]
    data["num_retries"] = policy["retries"]
    data["max_fallbacks"] = len(policy["fallbacks"])
    data["context_window_fallbacks"] = []
    data["content_policy_fallbacks"] = []
    metadata = data.setdefault("metadata", {})
    # Snapshot reasoning policy for this request: an edit cannot change a
    # request halfway through its fallback chain. Overwrite caller metadata.
    metadata["pl_task"] = task
    metadata["pl_reasoning"] = dict(policy["reasoning"])
    metadata["pl_models"] = [policy["primary"], *policy["fallbacks"]]
    metadata["tags"] = [*metadata.get("tags", []), "task:" + task]
    logger.info("llm_route task=%s primary=%s fallbacks=%s timeout=%s",
                task, policy["primary"], policy["fallbacks"], policy["timeout"])
    return data


def deployment_params(kwargs):
    metadata = kwargs.get("metadata") or (kwargs.get("litellm_params") or {}).get("metadata") or {}
    if metadata.get("pl_task"):
        model = str(kwargs.get("model", "")).split("/")[-1]
        if model not in metadata["pl_models"]:
            raise HTTPException(status_code=400, detail="Model is outside this task policy")
        # Remove caller and previous-provider thinking before applying this
        # deployment's policy. Reasoning is owned by the gateway.
        for key in (*GEMINI_ONLY_PARAMS, "reasoning_effort"):
            kwargs.pop(key, None)
        extra = kwargs.get("extra_body")
        if isinstance(extra, dict):
            for key in (*GEMINI_ONLY_PARAMS, "reasoning_effort"):
                extra.pop(key, None)
        effort = metadata["pl_reasoning"].get(model)
        if effort is not None:
            kwargs["reasoning_effort"] = effort
        if model == "gemini-3.8-flash":
            for cap in ("max_tokens", "max_completion_tokens"):
                if kwargs.get(cap) is not None:
                    kwargs[cap] = max(kwargs[cap], MIN_REASONING_COMPLETION_TOKENS)
    if (OPENAI_FALLBACK_MODEL.search(str(kwargs.get("model", "")))
            or (metadata.get("pl_task") and model == "gpt-5-mini")):
        return to_openai_params(kwargs)
    return kwargs if metadata.get("pl_task") else None


class OpenAIFallbackParams(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        if not str(data.get("model", "")).startswith("pl/"):
            return data
        try:
            return route_task(data, load_policies())
        except HTTPException:
            raise
        except (OSError, ValueError, KeyError, TypeError):
            logger.exception("Central LLM policy unavailable")
            raise HTTPException(status_code=503, detail="Central LLM policy unavailable")

    async def async_pre_call_deployment_hook(self, kwargs, call_type):
        return deployment_params(kwargs)


proxy_handler_instance = OpenAIFallbackParams()

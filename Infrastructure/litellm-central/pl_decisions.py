"""LiteLLM custom provider for typed yes/no decisions (Gemini + OpenAI Decisions APIs).

Services call a `pl/<task>` whose modality is "decision" with an ordinary chat
request: the system message is the yes/no question, the user message is the
evidence (text and images). This provider sends it to the deployment's
Decisions API and answers with chat content `{"probability": <0..1>, "model": <deployment>}`, so the
task policy, virtual keys, fallbacks and spend logging stay in the gateway.

Deployments (registered as `pldecision/<model_name>`):
  gemini-decision-1          -> POST generativelanguage.googleapis.com/v1beta/decisions
  openai-decision-<model>    -> POST api.openai.com/v1/decisions, model <model>
Provider keys come from the deployment's api_key. Image detail for Gemini comes
from the deployment's `extra_body.image_resolution` (low|medium|high|ultra_high).

Loaded via `custom_provider_map` in config.yaml and mounted read-only at
/app/pl_decisions.py by ~/litellm/run.sh. Edit here, then restart the gateway.
"""
import json
import time

import httpx
import litellm
from litellm.llms.custom_llm import CustomLLM, CustomLLMError

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/decisions"
OPENAI_URL = "https://api.openai.com/v1/decisions"
OPENAI_PREFIX = "openai-decision-"
RESOLUTIONS = ("low", "medium", "high", "ultra_high")
DEFAULT_TIMEOUT = 30.0


def split_messages(messages):
    """(question, parts) from a chat request: system text is the question,
    user content parts (text + image data URLs / https URLs) are the evidence."""
    question = " ".join(m["content"] for m in messages
                        if m.get("role") in ("system", "developer") and isinstance(m.get("content"), str)).strip()
    parts = []
    for message in messages:
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            parts.append({"type": "text", "text": content})
            continue
        for part in content or []:
            if part.get("type") == "text" and part.get("text"):
                parts.append({"type": "text", "text": part["text"]})
            elif part.get("type") == "image_url":
                url = part["image_url"]["url"] if isinstance(part.get("image_url"), dict) else part.get("image_url")
                parts.append({"type": "image", "url": url})
            else:
                raise CustomLLMError(status_code=400, message="Decision tasks accept only text and image input")
    if not question:
        raise CustomLLMError(status_code=400, message="Decision task needs the question as a system message")
    if not parts:
        raise CustomLLMError(status_code=400, message="Decision task needs user input")
    return question, parts


def _data_url(url):
    """(mime_type, base64) for a data URL, else None."""
    if not url.startswith("data:") or ";base64," not in url:
        return None
    header, data = url.split(",", 1)
    return header[5:].split(";")[0], data


def gemini_body(model, question, parts, resolution):
    blocks = []
    for part in parts:
        if part["type"] == "text":
            blocks.append({"type": "text", "text": part["text"]})
            continue
        inline = _data_url(part["url"])
        block = ({"type": "image", "data": inline[1], "mime_type": inline[0]} if inline
                 else {"type": "image", "uri": part["url"]})
        if resolution:
            block["resolution"] = resolution
        blocks.append(block)
    return {"model": model, "input": blocks,
            "questions": {"answer": {"type": "noul", "instructions": question}}}


def openai_body(model, question, parts):
    content = [{"type": "input_text", "text": p["text"]} if p["type"] == "text"
               else {"type": "input_image", "image_url": p["url"]} for p in parts]
    return {"model": model, "input": [{"role": "user", "content": content}],
            "questions": [{"type": "predicate", "name": "answer", "instructions": question}]}


def parse_gemini(payload):
    answer = (payload.get("answers") or {}).get("answer") or {}
    tokens = (payload.get("usage") or {}).get("total_input_tokens") or 0
    return answer.get("noul"), tokens


def parse_openai(payload):
    answers = payload.get("answers") or []
    answer = next((a for a in answers if a.get("name") == "answer"), {})
    if answer.get("type") == "refusal":
        raise CustomLLMError(status_code=502, message="Decision refused by provider")
    tokens = (payload.get("usage") or {}).get("input_tokens") or 0
    return answer.get("probability"), tokens


def provider_request(model_name, api_key, question, parts, resolution):
    """(url, headers, body, parser) for one deployment."""
    if model_name.startswith("gemini-"):
        return (GEMINI_URL, {"x-goog-api-key": api_key},
                gemini_body(model_name, question, parts, resolution), parse_gemini)
    if model_name.startswith(OPENAI_PREFIX):
        return (OPENAI_URL, {"Authorization": "Bearer " + api_key},
                openai_body(model_name[len(OPENAI_PREFIX):], question, parts), parse_openai)
    raise CustomLLMError(status_code=400, message="Unknown decision deployment")


def to_response(model_response, model_name, probability, tokens):
    if not isinstance(probability, (int, float)) or not 0 <= probability <= 1:
        raise CustomLLMError(status_code=502, message="Decision provider returned no probability")
    # The response model can echo the task alias, so the answering deployment travels in the content.
    model_response.choices[0].message.content = json.dumps({"probability": float(probability), "model": model_name})
    model_response.choices[0].finish_reason = "stop"
    model_response.model = model_name
    model_response.created = int(time.time())
    usage = litellm.Usage(prompt_tokens=int(tokens), completion_tokens=0, total_tokens=int(tokens))
    setattr(model_response, "usage", usage)
    return model_response


class DecisionProvider(CustomLLM):
    async def acompletion(self, model, messages, api_base, custom_prompt_dict, model_response, print_verbose,
                          encoding, api_key, logging_obj, optional_params, acompletion=None, litellm_params=None,
                          logger_fn=None, headers={}, timeout=None, client=None):
        if not api_key:
            raise CustomLLMError(status_code=500, message="Decision deployment has no provider key")
        model_name = model.split("/")[-1]
        extra = (optional_params or {}).get("extra_body") or {}
        resolution = extra.get("image_resolution")
        if resolution is not None and resolution not in RESOLUTIONS:
            raise CustomLLMError(status_code=500, message="Invalid image_resolution on decision deployment")
        question, parts = split_messages(messages)
        url, auth, body, parse = provider_request(model_name, api_key, question, parts, resolution)
        seconds = float(timeout) if isinstance(timeout, (int, float)) else DEFAULT_TIMEOUT
        try:
            async with httpx.AsyncClient(timeout=seconds) as http:
                reply = await http.post(url, headers={**auth, "Content-Type": "application/json"}, json=body)
        except httpx.TimeoutException as error:
            raise CustomLLMError(status_code=408, message="Decision provider timed out") from error
        except httpx.HTTPError as error:
            raise CustomLLMError(status_code=503, message="Decision provider unreachable") from error
        if reply.status_code != 200:
            # Provider text can name the policy that blocked an image; never the key.
            raise CustomLLMError(status_code=502 if reply.status_code < 500 else reply.status_code,
                                 message="Decision provider error %s: %s" % (reply.status_code, reply.text[:300]))
        probability, tokens = parse(reply.json())
        return to_response(model_response, model_name, probability, tokens)

    def completion(self, *args, **kwargs):
        raise CustomLLMError(status_code=400, message="Decision tasks are served asynchronously only")


decision_handler = DecisionProvider()

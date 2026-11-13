"""Offline checks for the decision provider: python3 test_pl_decisions.py."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest

for name in ('httpx', 'litellm', 'litellm.llms', 'litellm.llms.custom_llm'):
    sys.modules.setdefault(name, types.ModuleType(name))
if not hasattr(sys.modules['litellm.llms.custom_llm'], 'CustomLLM'):
    class CustomLLMError(Exception):
        def __init__(self, status_code, message):
            super().__init__(message)
            self.status_code = status_code
    sys.modules['litellm.llms.custom_llm'].CustomLLM = object
    sys.modules['litellm.llms.custom_llm'].CustomLLMError = CustomLLMError
spec = importlib.util.spec_from_file_location('pl_decisions', Path(__file__).with_name('pl_decisions.py'))
decisions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decisions)

MESSAGES = [
    {'role': 'system', 'content': 'Is a phone visible?'},
    {'role': 'user', 'content': [{'type': 'text', 'text': 'Webcam snapshot.'},
                                 {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,QUJD'}}]},
]


class DecisionProviderTests(unittest.TestCase):
    def test_gemini_request_carries_question_image_and_resolution(self):
        question, parts = decisions.split_messages(MESSAGES)
        url, headers, body, _ = decisions.provider_request('gemini-decision-1', 'k', question, parts, 'low')
        self.assertEqual(url, decisions.GEMINI_URL)
        self.assertEqual(headers, {'x-goog-api-key': 'k'})
        self.assertEqual(body['questions'], {'answer': {'type': 'noul', 'instructions': 'Is a phone visible?'}})
        self.assertEqual(body['input'][1], {'type': 'image', 'data': 'QUJD', 'mime_type': 'image/jpeg', 'resolution': 'low'})

    def test_openai_request_uses_predicate_and_model_suffix(self):
        question, parts = decisions.split_messages(MESSAGES)
        url, headers, body, _ = decisions.provider_request('openai-decision-gpt-6-luna', 'k', question, parts, None)
        self.assertEqual(url, decisions.OPENAI_URL)
        self.assertEqual(body['model'], 'gpt-6-luna')
        self.assertEqual(body['questions'][0]['type'], 'predicate')
        self.assertEqual(body['input'][0]['content'][1], {'type': 'input_image', 'image_url': 'data:image/jpeg;base64,QUJD'})

    def test_parsers_and_refusal(self):
        self.assertEqual(decisions.parse_gemini({'answers': {'answer': {'noul': 0.9}}, 'usage': {'total_input_tokens': 5}}), (0.9, 5))
        self.assertEqual(decisions.parse_openai({'answers': [{'name': 'answer', 'type': 'predicate', 'probability': 0.1}],
                                                'usage': {'input_tokens': 7}}), (0.1, 7))
        with self.assertRaises(decisions.CustomLLMError):
            decisions.parse_openai({'answers': [{'name': 'answer', 'type': 'refusal'}]})

    def test_response_names_the_answering_deployment(self):
        import json as _json
        message = types.SimpleNamespace(content=None)
        response = types.SimpleNamespace(choices=[types.SimpleNamespace(message=message, finish_reason=None)])
        decisions.litellm.Usage = lambda **kw: kw
        decisions.to_response(response, 'openai-decision-gpt-6-luna', 0.25, 9)
        self.assertEqual(_json.loads(message.content), {'probability': 0.25, 'model': 'openai-decision-gpt-6-luna'})
        with self.assertRaises(decisions.CustomLLMError):
            decisions.to_response(response, 'gemini-decision-1', None, 0)

    def test_bad_input_fails_explicitly(self):
        with self.assertRaises(decisions.CustomLLMError):
            decisions.split_messages([MESSAGES[1]])
        with self.assertRaises(decisions.CustomLLMError):
            decisions.split_messages([MESSAGES[0], {'role': 'user', 'content': [{'type': 'input_audio'}]}])
        with self.assertRaises(decisions.CustomLLMError):
            decisions.provider_request('gpt-6-luna', 'k', 'q', [], None)


if __name__ == '__main__':
    unittest.main()

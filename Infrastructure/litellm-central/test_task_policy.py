"""Offline policy regression checks: python3 test_task_policy.py."""
import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest

try:
    import fastapi
except ImportError:
    fastapi = types.ModuleType('fastapi')
    class HTTPException(Exception):
        def __init__(self, status_code, detail):
            self.status_code, self.detail = status_code, detail
    fastapi.HTTPException = HTTPException
    sys.modules['fastapi'] = fastapi

module = types.ModuleType('litellm.integrations.custom_logger')
module.CustomLogger = object
sys.modules['litellm.integrations.custom_logger'] = module
spec = importlib.util.spec_from_file_location('policy', Path(__file__).with_name('pl_openai_fallback.py'))
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)

class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tasks = policy.load_policies()

    def test_caller_cannot_override_task_routing_or_reasoning(self):
        data = policy.route_task({'model':'pl/interview-final-score', 'fallbacks':[{'model':'wrong'}],
                                 'timeout':600, 'num_retries':9,
                                 'metadata':{'pl_reasoning':{'gpt-6-luna':'none'}}}, self.tasks)
        self.assertEqual(data['fallbacks'], [{'model':'gpt-6-luna'}])
        self.assertEqual(data['timeout'],120)
        self.assertEqual(data['num_retries'],0)
        result = policy.deployment_params({'model':'openai/gpt-6-luna', 'metadata':data['metadata'],
                                          'reasoning_effort':'disable', 'temperature':0.5, 'max_tokens':200})
        self.assertEqual(result['reasoning_effort'],'low')
        self.assertEqual(result['max_completion_tokens'],4096)
        self.assertNotIn('temperature', result)

    def test_gemini_and_openai_get_different_settings_for_same_task(self):
        data = policy.route_task({'model':'pl/communication-score'}, self.tasks)
        gemini = policy.deployment_params({'model':'gemini/gemini-3.8-flash','metadata':data['metadata'],
                                           'reasoning_effort':'disable','thinking_config':{'thinking_budget':0}})
        self.assertEqual(gemini['reasoning_effort'],'low')
        self.assertNotIn('thinking_config',gemini)
        openai = policy.deployment_params({'model':'openai/gpt-6-luna','metadata':data['metadata'],
                                          'reasoning_effort':'disable','temperature':0})
        self.assertEqual(openai['extra_body']['reasoning_effort'],'none')

    def test_listener_and_grounding_cannot_fall_back_to_text_only_model(self):
        for task in ['pl/interview-listener','pl/reading-audio','pl/corporate-web-search']:
            candidate=copy.deepcopy(self.tasks[task]);candidate['fallbacks'].append('gpt-6-luna')
            with self.assertRaises(ValueError): policy.validate_policy(task,candidate)
        audio = policy.route_task({'model':'pl/interview-listener'},self.tasks)
        self.assertEqual(audio['max_fallbacks'],2)
        self.assertEqual(audio['fallbacks'],[{'model':'gemini-3.8-flash'},{'model':'gemini-2.5-flash'}])

    def test_unknown_task_fails_closed_and_legacy_calls_unchanged(self):
        with self.assertRaises(policy.HTTPException):policy.route_task({'model':'pl/typo'},self.tasks)
        data={'model':'gemini-2.5-flash','timeout':42}
        self.assertEqual(policy.route_task(copy.deepcopy(data),self.tasks),data)
        self.assertIsNone(policy.deployment_params({'model':'gemini/gemini-2.5-flash'}))

    def test_router_cannot_escape_audio_task_chain(self):
        data=policy.route_task({'model':'pl/interview-listener'},self.tasks)
        with self.assertRaises(policy.HTTPException):
            policy.deployment_params({'model':'openai/gpt-6-luna','metadata':data['metadata']})
        with self.assertRaises(policy.HTTPException):
            policy.route_task({'model':'pl/interview-probe','messages':[{'content':[{'type':'input_audio'}]}]},self.tasks)

    def test_all_policies_valid_and_live_turns_have_short_deadlines(self):
        for task, candidate in self.tasks.items(): policy.validate_policy(task,candidate)
        self.assertEqual(self.tasks['pl/interview-probe']['timeout'],6)
        must_ask=self.tasks['pl/interview-must-ask']
        self.assertEqual(must_ask['timeout'],4 if must_ask['primary']=='gemini-3.1-flash-lite' else 6)

if __name__=='__main__':unittest.main()

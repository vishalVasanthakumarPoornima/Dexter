import os
import unittest

from backend.models.ollama_client import llm_status


class LLMRoutingTests(unittest.TestCase):
    def setUp(self):
        self.original_env = {
            key: os.environ.get(key)
            for key in {
                "DEXTER_LLM_PROVIDER",
                "DEXTER_OPENROUTER_API_KEY",
                "OPENROUTER_API_KEY",
            }
        }

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_auto_uses_local_when_openrouter_key_is_missing(self):
        os.environ["DEXTER_LLM_PROVIDER"] = "auto"
        os.environ.pop("DEXTER_OPENROUTER_API_KEY", None)
        os.environ.pop("OPENROUTER_API_KEY", None)

        status = llm_status()

        self.assertFalse(status["cloud"]["configured"])
        self.assertEqual(status["routing"]["local_chat"], "ollama")
        self.assertEqual(status["routing"]["online_tasks"], "ollama")

    def test_auto_routes_online_tasks_to_openrouter_when_key_exists(self):
        os.environ["DEXTER_LLM_PROVIDER"] = "auto"
        os.environ["DEXTER_OPENROUTER_API_KEY"] = "test-key"
        os.environ.pop("OPENROUTER_API_KEY", None)

        status = llm_status()

        self.assertTrue(status["cloud"]["configured"])
        self.assertEqual(status["routing"]["local_chat"], "ollama")
        self.assertEqual(status["routing"]["online_tasks"], "openrouter")


if __name__ == "__main__":
    unittest.main()

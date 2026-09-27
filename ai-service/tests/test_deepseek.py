import unittest
from unittest.mock import patch

from app.core.config import settings
from app.llm.deepseek import DeepSeekConfigurationError, create_chat_model


class DeepSeekProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        self._values = (settings.deepseek_api_key, settings.deepseek_base_url, settings.deepseek_model)

    def tearDown(self) -> None:
        settings.deepseek_api_key, settings.deepseek_base_url, settings.deepseek_model = self._values

    def test_requires_complete_configuration(self) -> None:
        settings.deepseek_api_key = "test-key"
        settings.deepseek_base_url = ""
        settings.deepseek_model = "test-model"

        with self.assertRaises(DeepSeekConfigurationError):
            create_chat_model()

    def test_constructs_langchain_model_without_network_request(self) -> None:
        settings.deepseek_api_key = "test-key"
        settings.deepseek_base_url = "test-base-url"
        settings.deepseek_model = "test-model"
        with patch("langchain_openai.ChatOpenAI") as chat_model:
            create_chat_model()

        chat_model.assert_called_once_with(
            api_key="test-key",
            base_url="test-base-url",
            model="test-model",
            timeout=settings.request_timeout_seconds,
            max_retries=1,
        )

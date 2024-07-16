# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Vertex AI LLM provider."""

import vertexai.preview.generative_models as generative_models
from google.cloud import aiplatform
from vertexai.preview.generative_models import GenerativeModel

from . import interface, manager


class VertexAI(interface.LLMProvider):
    """Vertex AI LLM provider."""

    NAME = "vertexai"

    def count_tokens(self, prompt: str):
        """
        Count the number of tokens in a prompt using the Vertex AI service.

        Args:
            prompt: The prompt to count the tokens for.

        Returns:
            The number of tokens in the prompt.
        """
        model = GenerativeModel(self.config.get("model"))
        return model.count_tokens(prompt)

    def generate(self, prompt: str) -> str:
        """
        Generate text using the Vertex AI service.

        Args:
            prompt: The prompt to use for the generation.
            temperature: The temperature to use for the generation.
            stream: Whether to stream the generation or not.

        Returns:
            The generated text as a string.
        """
        aiplatform.init(
            project=self.config.get("project_id"),
        )
        model = GenerativeModel(self.config.get("model"))

        # Safety config
        safety_config = {
            generative_models.HarmCategory.HARM_CATEGORY_HATE_SPEECH: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            generative_models.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            generative_models.HarmCategory.HARM_CATEGORY_HARASSMENT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            generative_models.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
        }

        response = model.generate_content(
            prompt,
            generation_config={
                "max_output_tokens": self.config.get("max_output_tokens"),
                "temperature": self.config.get("temperature"),
            },
            safety_settings=safety_config,
            stream=self.config.get("stream"),
        )

        return response.text


manager.LLMManager.register_provider(VertexAI)

import os
import json
import csv
import requests
from typing import Optional, Dict, Any

from haystack import component

@component
class AzureOpenAIGenerator:
    """
    Haystack component that calls Azure OpenAI Chat Completions via REST,
    returning {"response": "<assistant text>"} to match your OllamaGenerator contract.
    """

    def __init__(
        self,
        full_prompt_file: Optional[str] = None,
        temperature: float = 1.0,
        max_completion_tokens: Optional[int] = 40000,
        timeout_s: int = 300,
    ):
        self.api_key = os.environ.get("UIO_SE_GROUP_GPT_API_KEY")
        self.resource_name = os.environ.get("UIO_SE_GROUP_GPT_RESOURCE_NAME")
        self.deployment_name = os.environ.get("UIO_SE_GROUP_GPT_DEPLOYMENT_NAME")
        self.api_version = os.environ.get("UIO_SE_GROUP_API_VERSION")

        if not self.api_key or not self.resource_name or not self.deployment_name or not self.api_version:
            raise ValueError(
                "Missing Azure OpenAI configuration. Ensure these are set:\n"
                "- UIO_SE_GROUP_GPT_API_KEY\n"
                "- UIO_SE_GROUP_GPT_RESOURCE_NAME\n"
                "- UIO_SE_GROUP_GPT_DEPLOYMENT_NAME\n"
                "- UIO_SE_GROUP_API_VERSION"
            )

        self.endpoint_url = (
            f"https://{self.resource_name}.openai.azure.com/"
            f"openai/deployments/{self.deployment_name}/chat/completions?api-version={self.api_version}"
        )

        self.headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }

        self.full_prompt_file = full_prompt_file
        self.temperature = temperature
        self.max_completion_tokens = max_completion_tokens
        self.timeout_s = timeout_s

    @component.output_types(response=str, raw=dict)
    def run(self, prompt: str) -> Dict[str, Any]:
        if self.full_prompt_file:
            with open(self.full_prompt_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([prompt])

        body: Dict[str, Any] = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
        }

        if self.max_completion_tokens is not None:
            body["max_completion_tokens"] = self.max_completion_tokens

        resp = requests.post(
            self.endpoint_url,
            headers=self.headers,
            data=json.dumps(body),
            timeout=self.timeout_s,
        )

        try:
            resp_json = resp.json()
        except json.JSONDecodeError:
            raise RuntimeError(
                f"Azure OpenAI response was not JSON (status={resp.status_code}). Body:\n{resp.text}"
            )

        if resp.status_code >= 400 or "error" in resp_json:
            err = resp_json.get("error", resp_json)
            raise RuntimeError(
                f"Azure OpenAI API error (status={resp.status_code}). Details:\n{json.dumps(err, indent=2)}"
            )

        try:
            content = resp_json["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(
                f"Unexpected Azure OpenAI response shape: {json.dumps(resp_json, indent=2)}"
            ) from e
        
        usage = resp_json.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")


        return {"response": content, "raw": resp_json, "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": total_tokens}

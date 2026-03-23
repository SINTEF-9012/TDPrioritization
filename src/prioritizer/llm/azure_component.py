import os
import json
import csv
import requests
from typing import Optional, Dict, Any

from haystack import component


@component
class AzureOpenAIGenerator:
    """
    Haystack component that supports both:
    - Azure Chat Completions deployments
    - Azure Responses API deployments (e.g. Codex-style deployments)

    Returns:
        {
            "response": "<assistant text>",
            "raw": <raw json>,
            "prompt_tokens": int | None,
            "completion_tokens": int | None,
            "total_tokens": int | None,
        }
    """

    def __init__(
        self,
        deployment: str,
        full_prompt_file: Optional[str] = None,
        temperature: float = 1.0,
        max_completion_tokens: Optional[int] = 40000,
        timeout_s: int = 300,
    ):
        self.api_key = os.environ.get("UIO_SE_GROUP_GPT_API_KEY")
        self.resource_name = os.environ.get("UIO_SE_GROUP_GPT_RESOURCE_NAME")
        self.deployment_name = deployment
        self.timeout_s = timeout_s
        self.temperature = temperature
        self.max_completion_tokens = max_completion_tokens
        self.full_prompt_file = full_prompt_file
        self.deployment = None

        if self.deployment_name == "gpt-3.5":
            self.api_version = os.environ.get("UIO_SE_GROUP_API_VERSION")
            self.deployment = os.environ.get("UIO_SE_GROUP_GPT_DEPLOYMENT_NAME")

        elif self.deployment_name == "codex":
            self.api_version = os.environ.get("UIO_SE_GROUP_API_VERSION_CODEX")
            self.deployment = os.environ.get("UIO_SE_GROUP_CODEX_DEPLOYMENT_NAME")

        else:
            raise ValueError("Deployment currently only supports gpt-4 or codex")

        if not self.api_key or not self.resource_name or not self.deployment_name or not self.api_version:
            raise ValueError(
                "Missing Azure OpenAI configuration. Ensure these are set."
            )

        if self.deployment_name == "gpt-3.5":
            self.endpoint_url = (
                f"https://{self.resource_name}.openai.azure.com/"
                f"openai/deployments/{self.deployment}/chat/completions"
                f"?api-version={self.api_version}"
            )
            self.headers = {
                "api-key": self.api_key,
                "Content-Type": "application/json",
            }
        else:
            self.endpoint_url = (
                f"https://{self.resource_name}.openai.azure.com/"
                f"openai/responses?api-version={self.api_version}"
            )
            self.headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

    def _build_body(self, prompt: str) -> Dict[str, Any]:
        if self.deployment_name == "gpt-3.5":
            body: Dict[str, Any] = {
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self.temperature,
            }
            if self.max_completion_tokens is not None:
                body["max_completion_tokens"] = self.max_completion_tokens
            return body

        # Responses API mode
        body = {
            "model": self.deployment,
            "input": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
        }
        if self.max_completion_tokens is not None:
            body["max_output_tokens"] = self.max_completion_tokens
        return body

    def _extract_chat_text(self, resp_json: Dict[str, Any]) -> str:
        try:
            return resp_json["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(
                f"Unexpected Azure Chat Completions response shape:\n{json.dumps(resp_json, indent=2)}"
            ) from e

    def _extract_responses_text(self, resp_json: Dict[str, Any]) -> str:
        try:
            for item in resp_json.get("output", []):
                if item.get("type") == "message":
                    for content_item in item.get("content", []):
                        if content_item.get("type") in {"output_text", "text"}:
                            return str(content_item.get("text", "")).strip()
            raise RuntimeError("No output text found in Responses API payload.")
        except Exception as e:
            raise RuntimeError(
                f"Unexpected Azure Responses API response shape:\n{json.dumps(resp_json, indent=2)}"
            ) from e

    def _extract_usage(self, resp_json: Dict[str, Any]) -> Dict[str, Optional[int]]:
        usage = resp_json.get("usage", {}) or {}

        if self.deployment_name == "gpt-3.5":
            return {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
            }

        output_tokens = usage.get("output_tokens")
        return {
            "prompt_tokens": usage.get("input_tokens"),
            "completion_tokens": output_tokens,
            "total_tokens": usage.get("total_tokens"),
        }

    @component.output_types(
        response=str,
        raw=dict,
        prompt_tokens=Optional[int],
        completion_tokens=Optional[int],
        total_tokens=Optional[int],
    )
    def run(self, prompt: str) -> Dict[str, Any]:
        if self.full_prompt_file:
            with open(self.full_prompt_file, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([prompt])

        body = self._build_body(prompt)

        resp = requests.post(
            self.endpoint_url,
            headers=self.headers,
            json=body,
            timeout=self.timeout_s,
        )

        try:
            resp_json = resp.json()
        except json.JSONDecodeError:
            raise RuntimeError(
                f"Azure OpenAI response was not JSON (status={resp.status_code}). Body:\n{resp.text}"
            )

        if resp.status_code >= 400 or resp_json.get("error"):
            err = resp_json.get("error", resp_json)
            raise RuntimeError(
                f"Azure OpenAI API error (status={resp.status_code}). Details:\n{json.dumps(err, indent=2)}"
            )

        if self.deployment_name == "gpt-3.5":
            content = self._extract_chat_text(resp_json)
        else:
            content = self._extract_responses_text(resp_json)

        usage_info = self._extract_usage(resp_json)

        return {
            "response": content,
            "raw": resp_json,
            "prompt_tokens": usage_info["prompt_tokens"],
            "completion_tokens": usage_info["completion_tokens"],
            "total_tokens": usage_info["total_tokens"],
        }
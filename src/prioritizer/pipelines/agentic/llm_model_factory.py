import os
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from langchain_ollama import ChatOllama


def build_llm(args):

    if args.llm_provider == "ollama":
        return ChatOllama(
            model=args.ollama_model,
            validate_model_on_init=True,
            temperature=0,
        )

    resource_name = os.environ["UIO_SE_GROUP_GPT_RESOURCE_NAME"]
    api_key = os.environ["UIO_SE_GROUP_GPT_API_KEY"]

    if args.deployment == "gpt-3.5":
        deployment = os.environ["UIO_SE_GROUP_GPT_DEPLOYMENT_NAME"]
        api_version = os.environ["UIO_SE_GROUP_API_VERSION"]

        return AzureChatOpenAI(
            azure_endpoint=f"https://{resource_name}.openai.azure.com/",
            api_key=api_key,
            azure_deployment=deployment,
            api_version=api_version,
            temperature=1,
            max_tokens=40000,
            timeout=None,
            max_retries=2,
        )

    if args.deployment == "codex":
        deployment = os.environ["UIO_SE_GROUP_CODEX_DEPLOYMENT_NAME"]
        api_version = os.environ["UIO_SE_GROUP_API_VERSION_CODEX"] 

        return ChatOpenAI(
            model=deployment,
            base_url=f"https://{resource_name}.openai.azure.com/openai/v1/",
            api_key=api_key,
            use_responses_api=True,
            temperature=1,
            max_tokens=40000,
            timeout=None,
            max_retries=2,
        )

    raise ValueError(f"Unsupported Azure API")
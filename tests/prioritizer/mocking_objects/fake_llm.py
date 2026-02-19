from dataclasses import dataclass
from langchain_core.messages import AIMessage

@dataclass
class FakeLLM:
    response_text: str
    last_messages: list = None

    def invoke(self, messages):
        self.last_messages = messages
        return AIMessage(content=self.response_text)

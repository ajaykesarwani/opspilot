import os
import json
from typing import Protocol, Type, TypeVar, Any
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

class ProviderTimeoutError(Exception):
    pass

class LLMProvider(Protocol):
    def generate_structured(self, prompt: str, schema: Type[T]) -> T:
        ...

class MockLLMProvider:
    def __init__(self):
        pass
        
    def generate_structured(self, prompt: str, schema: Type[T]) -> T:
        # Simple deterministic mock response
        # If 'insufficient' in prompt, we might want to trigger the insufficient evidence response.
        if "INSUFFICIENT_EVIDENCE: True" in prompt:
            data = {
                "summary": "Insufficient information to answer.",
                "requested_action": "None",
                "missing_information": "Context is lacking details.",
                "recommended_next_step": "Request more information.",
                "confidence_category": "insufficient_evidence",
                "citations": [],
                "limitation_disclaimer": "This is a mock abstention response."
            }
        else:
            data = {
                "summary": "Mock summary based on context.",
                "requested_action": "Mock approved action.",
                "missing_information": None,
                "recommended_next_step": "Proceed with action.",
                "confidence_category": "high",
                "citations": ["doc1"],
                "limitation_disclaimer": "This is a mock response."
            }
        return schema(**data)

def get_llm_provider() -> LLMProvider:
    mock_mode = os.environ.get("MOCK_MODE", "true").lower() == "true"
    if mock_mode:
        return MockLLMProvider()
    else:
        # Optional real provider adapter could go here
        raise NotImplementedError("Real LLM provider not yet implemented.")

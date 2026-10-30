import os
from typing import Type, TypeVar

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel
from langsmith import wrappers

load_dotenv()

MODEL = os.getenv("LLM_MODEL", "gemini-3.5-flash")
client = wrappers.wrap_gemini(genai.Client())

T = TypeVar("T", bound=BaseModel)   

# function that takes in the prompt, content, and shape of the reponse
def structured(system: str, content: str, schema: Type[T]) -> T:
    """Call the model and get back a validated Pydantic object."""

    # Send everything to Gemini
    response = client.models.generate_content(
        model=MODEL,                                  # which Gemini model (from .env)
        contents=content,                                # content being passed in
        config=types.GenerateContentConfig(
            system_instruction=system,                # the agent's job description
            response_mime_type="application/json",    # answer in JSON, not prose
            response_schema=schema,                   # the form it must fill in
            temperature=0,                            # consistent answers
        ),
    )

    # Usually the SDK already turned the JSON into an object of `schema`
    if response.parsed is not None:
        return response.parsed

    # If not, have Pydantic convert + check the raw JSON text ourselves
    return schema.model_validate_json(response.text)
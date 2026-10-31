import os
import uuid
from pathlib import Path

from google.genai import types

from tutor import llm

IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gemini-3.1-flash-image")
IMAGES_DIR = Path(__file__).resolve().parents[2] / "generated_images"  # repo root, git-ignored

# added in front of every prompt so the images look like they belong together
STYLE = (
    "Simple, clean educational illustration with flat colors, clear labels, "
    "and a plain light background. "
)

EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}


def generate_image(prompt: str) -> str | None:
    """Draw an image for the prompt, save it to IMAGES_DIR, and return its file name (None if no image came back)."""
    response = llm.client.models.generate_content(
        model=IMAGE_MODEL,
        contents=STYLE + prompt,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),  # ask for a picture, not text
    )

    # the image comes back as raw bytes inside one of the response parts
    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.data:
            name = uuid.uuid4().hex + EXTENSIONS.get(part.inline_data.mime_type, ".png")
            IMAGES_DIR.mkdir(exist_ok=True)
            (IMAGES_DIR / name).write_bytes(part.inline_data.data)
            return name  # just the file name; the API decides what URL it's served at

    return None

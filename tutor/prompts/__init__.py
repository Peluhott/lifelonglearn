from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


def load(name: str) -> str:
    """Read a prompt from tutor/prompts/<name>.md."""
    return (PROMPTS_DIR / f"{name}.md").read_text().strip()

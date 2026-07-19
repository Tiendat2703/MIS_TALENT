"""Shared UTF-8 prompt loader for all pipeline agents."""

from pathlib import Path


SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"


def load_prompt(filename: str | Path) -> str:
    candidate = Path(filename)
    path = candidate if candidate.is_absolute() else SKILLS_DIR / candidate
    prompt = path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise RuntimeError(f"Agent prompt is empty: {path}")
    return prompt


load_agent_prompt = load_prompt


__all__ = ["load_agent_prompt", "load_prompt"]

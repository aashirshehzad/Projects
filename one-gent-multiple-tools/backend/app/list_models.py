"""Print the Gemini model ids available to your key:  python -m app.list_models"""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from .agent import Agent  # noqa: E402


def main() -> None:
    try:
        agent = Agent()
    except RuntimeError as exc:
        print(exc)
        return
    models = agent.available_models()
    if not models:
        print("Could not list models (check your GEMINI_API_KEY).")
        return
    print(f"Models available for generateContent (current GEMINI_MODEL = {agent.model}):\n")
    for m in models:
        print(f"  {m}")


if __name__ == "__main__":
    main()

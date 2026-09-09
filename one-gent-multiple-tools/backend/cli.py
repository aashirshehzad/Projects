"""Terminal chat with the agent:  python cli.py"""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from app.agent import Agent  # noqa: E402


def main() -> None:
    try:
        agent = Agent()
    except RuntimeError as exc:
        print(f"[setup] {exc}")
        return

    print(f"one-agent-multiple-tools  (model: {agent.model})")
    print("Ask about weather, stocks, math, unit/currency conversion, Wikipedia,")
    print("the web, the time, word definitions, or the news.  Ctrl+C to quit.\n")

    history: list[dict] = []
    while True:
        try:
            msg = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not msg:
            continue

        try:
            result = agent.run(msg, history)
        except RuntimeError as exc:
            print(f"\n[error] {exc}\n")
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"\n[error] {type(exc).__name__}: {exc}\n")
            continue
        for step in result["steps"]:
            print(f"  · {step['tool']}({step['args']})")
        print(f"\nbot > {result['reply']}\n")

        history.append({"role": "user", "content": msg})
        history.append({"role": "assistant", "content": result["reply"]})


if __name__ == "__main__":
    main()

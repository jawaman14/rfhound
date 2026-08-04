"""The AI menu — an interactive copilot console for RFHound.

Reached via ``rfhound ai``. A chat REPL on top of the existing safe copilot
(``llm/``): you type natural language, it runs **receive-and-analyse** actions
only (no transmit, no code execution). Kept separate from the main menu.

Slash commands:
  /help            show commands
  /actions         list the actions the copilot may call
  /provider NAME   switch backend (offline | anthropic | local)
  /history         show this session's turns
  /clear           clear history
  /quit            leave the AI console
"""

from __future__ import annotations

from . import console
from .config import Config
from .llm import Copilot, actions as llm_actions


HELP = (
    "Ask in plain English, e.g. 'is there a jammer on 433?', 'scan for drones', "
    "'check for an IMSI catcher', 'what's at 1090 MHz?'.\n"
    "Commands: /help  /actions  /provider <offline|anthropic|local>  /history  /clear  /quit"
)


def _print_result(result) -> None:
    for a in result.actions_run:
        console.info(f"ran {a['action']}({a.get('params', {})})")
    if result.text:
        console.print_(result.text)


def run_ai_menu(cfg: Config, provider: str | None = None) -> int:
    copilot = Copilot(cfg, provider=provider)
    console.rule("RFHound — AI copilot console")
    console.print_(f"Provider: [bold]{copilot.provider}[/bold]  ·  receive-and-analyse only "
                   "(no transmit, no code execution)" if console.have_rich()
                   else f"Provider: {copilot.provider}  ·  receive-and-analyse only")
    console.print_(HELP)
    history: list = []
    while True:
        try:
            q = console.ask("ai").strip()
        except (KeyboardInterrupt, EOFError):
            console.print_("")
            return 0
        if not q:
            continue
        low = q.lower()
        if low in ("/quit", "/q", "/exit", "quit", "exit"):
            return 0
        if low in ("/help", "help", "?"):
            console.print_(HELP)
            continue
        if low in ("/actions", "actions"):
            rows = [[a.name, a.description] for a in llm_actions.ACTIONS.values()]
            console.table("Copilot actions (all receive-only)", ["Action", "What it does"], rows)
            continue
        if low.startswith("/provider"):
            parts = q.split()
            if len(parts) == 2 and parts[1] in ("offline", "anthropic", "local"):
                copilot = Copilot(cfg, provider=parts[1])
                console.success(f"Switched to provider '{copilot.provider}'.")
            else:
                console.warn("Usage: /provider offline|anthropic|local")
            continue
        if low in ("/history", "history"):
            if not history:
                console.print_("(no history yet)")
            for i, (u, r) in enumerate(history, 1):
                console.print_(f"{i}. you: {u}")
                console.print_(f"   ai: {r[:200]}")
            continue
        if low in ("/clear", "clear"):
            history.clear()
            console.success("History cleared.")
            continue
        # Otherwise: send to the copilot.
        try:
            result = copilot.ask(q)
        except Exception as exc:  # never crash the console on a provider error
            console.error(f"Copilot error: {exc}")
            if copilot.provider != "offline":
                console.print_("Tip: check your API key / endpoint, or '/provider offline'.")
            continue
        _print_result(result)
        history.append((q, result.text))

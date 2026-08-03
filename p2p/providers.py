"""Where the models come from. One file, so nothing else has to know.

Two providers:

  ollama     a model running on your own machine. Free, offline, slower, and
             the weaker models cannot do every job (see README.md).
  deepseek   the DeepSeek API. Costs money, needs a key, but it is far more
             capable and it answers several calls at once, which the local
             server does not.

Everything else in the project asks for a client and does not care which of
these it got.

THE KEY NEVER GOES IN A TRACKED FILE. This folder is a git repository, so a key
written into config.yaml or a source file would be committed and shared. Two
safe places, checked in this order:

  1. your shell environment

        PowerShell   $env:DEEPSEEK_API_KEY = "sk-..."
        cmd          set DEEPSEEK_API_KEY=sk-...
        Git Bash     export DEEPSEEK_API_KEY=sk-...

  2. a `.env` file next to config.yaml, copied from `.env.example`

        DEEPSEEK_API_KEY=sk-...

`.env` is listed in .gitignore, so it is never committed. The environment wins
when both are set, so a key you just exported is never silently overridden by
a stale file.
"""

from __future__ import annotations

import os
from pathlib import Path

from autogen_core.models import ModelInfo
from autogen_ext.models.ollama import OllamaChatCompletionClient
from autogen_ext.models.openai import OpenAIChatCompletionClient

PROVIDERS = ("ollama", "deepseek")

# DeepSeek speaks the same shape as the OpenAI API, so the OpenAI client works
# once it is pointed at their address.
DEEPSEEK_URL = "https://api.deepseek.com/v1"
DEEPSEEK_KEY_ENV = "DEEPSEEK_API_KEY"

# A sensible model for each provider, used only when the config does not name
# one. These are the models measured in README.md, 'Which model to use'.
DEFAULT_MODEL = {
    # qwen2.5:14b measured best of the local models: right every time, kept the
    # answer format every time, and defended a lie without giving the game away.
    # See 'Which model to use' in README.md for the measurements.
    "ollama": "qwen2.5:14b",
    "deepseek": "deepseek-v4-pro",
}

# Our agents read and write plain text. We never ask for tool calls or for the
# model to return JSON itself, so all of these stay off for both providers.
# Keeping them the same either way means a change of provider cannot quietly
# change how a reply is produced.
_PLAIN_TEXT = ModelInfo(
    vision=False,
    function_calling=False,
    json_output=False,
    family="unknown",
    structured_output=False,
)


def read_env_file(path=None) -> dict:
    """Read simple KEY=VALUE lines out of a .env file.

    Twelve lines instead of a new package. We only need the plain form that
    `.env.example` shows, so there is nothing here for quoting rules or
    variable expansion to get wrong.

    Blank lines and lines starting with # are skipped. A line with no `=` is
    skipped rather than raising, so a stray note in the file cannot stop a run.
    """
    file = Path(path) if path else Path(__file__).resolve().parent.parent / ".env"
    if not file.exists():
        return {}
    found = {}
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        # Strip quotes people add out of habit; a real key has none.
        found[name.strip()] = value.strip().strip("\"'")
    return found


def deepseek_key() -> str:
    """Read the DeepSeek key, or stop with instructions.

    Two places are checked, in this order:

      1. the environment, so a key set in your shell always wins
      2. a `.env` file next to config.yaml, which is what `.env.example` is
         showing you how to write

    The environment wins on purpose. Otherwise a stale `.env` would quietly
    override the key you just exported, and you would be debugging the wrong
    one.

    This is checked BEFORE the run starts. Otherwise the failure arrives after
    the agents are built and the first question is already on screen, which
    looks like a bug in the network rather than a missing key.
    """
    key = os.environ.get(DEEPSEEK_KEY_ENV, "").strip()
    if not key:
        key = read_env_file().get(DEEPSEEK_KEY_ENV, "").strip()
    # The placeholder from .env.example is not a key. Catching it here saves a
    # confusing 401 from the API.
    if key and key.upper().startswith("YOUR_API_KEY"):
        raise SystemExit(
            f"\n.env still has the example value for {DEEPSEEK_KEY_ENV}.\n"
            "Replace YOUR_API_KEY_GOES_HERE with your real key.")
    if not key:
        raise SystemExit(
            f"\n{DEEPSEEK_KEY_ENV} is not set, but provider is 'deepseek'.\n\n"
            "Either put it in a .env file next to config.yaml:\n"
            f"  {DEEPSEEK_KEY_ENV}=sk-...\n\n"
            "or set it in your shell:\n"
            f"  PowerShell   $env:{DEEPSEEK_KEY_ENV} = \"sk-...\"\n"
            f"  cmd          set {DEEPSEEK_KEY_ENV}=sk-...\n"
            f"  Git Bash     export {DEEPSEEK_KEY_ENV}=sk-...\n\n"
            "Do not put the key in config.yaml - that file is committed to git,\n"
            "while .env is ignored.\n"
            "To run offline instead, set  provider: \"ollama\"  in the config.")
    return key


def make_client(provider: str, model: str, seed: int | None = None):
    """Build the model client for one provider.

    `seed` makes the model itself repeatable. Without it the same question can
    get a different answer every time, so no run can be reproduced - which was
    true of this project until now, even though the config had a `seed`
    setting. That setting only ever chose which agent was the liar.

    Measured on qwen2.5:14b, asking for an invented name three times:
        no seed   'Stardust Whisperer', 'Zephyrion', 'Zephyrion'
        seed 42   'WhisperWings', 'WhisperWings', 'WhisperWings'
        seed 99   'Whisperwraith'      (a different seed gives a different run)
    """
    if provider == "deepseek":
        # The OpenAI-shaped API takes a seed, but treats it as best effort:
        # the same seed usually gives the same answer and is not promised to.
        # Ollama's seed is exact.
        extra = {"seed": seed} if seed is not None else {}
        return OpenAIChatCompletionClient(
            model=model,
            base_url=DEEPSEEK_URL,
            api_key=deepseek_key(),
            model_info=_PLAIN_TEXT,
            # Reasoning responses can legitimately take several minutes under
            # concurrent load. The library default timed out completed work and
            # forced whole 100-question scenarios to restart.
            timeout=600.0,
            max_retries=3,
            **extra,
        )
    if provider == "ollama":
        # Ollama models are not in AutoGen's built-in list, so we have to say
        # what they can do.
        options = {"seed": seed} if seed is not None else {}
        return OllamaChatCompletionClient(model=model, model_info=_PLAIN_TEXT,
                                          options=options)
    raise SystemExit(f"unknown provider '{provider}'. "
                     f"choose one of: {', '.join(PROVIDERS)}")


def check_ready(provider: str) -> None:
    """Fail early if this provider cannot possibly work.

    Called once before any agent is built, so a missing key costs a second
    instead of half a run.
    """
    if provider == "deepseek":
        deepseek_key()


def describe(provider: str, model: str) -> str:
    """One line for the run header, so the log says where the answers came from."""
    if provider == "deepseek":
        return f"deepseek API ({model})   calls run side by side"
    return f"local ollama ({model})   calls are mostly one at a time"

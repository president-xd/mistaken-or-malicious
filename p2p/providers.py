"""Where the models come from. One file, so nothing else has to know.

Two providers:

  ollama     a model running on your own machine. Free, offline, slower, and
             the weaker models cannot do every job (see TEST_REPORT.md).
  deepseek   the DeepSeek API. Costs money, needs a key, but it is far more
             capable and it answers several calls at once, which the local
             server does not.

Everything else in the project asks for a client and does not care which of
these it got.

THE KEY NEVER GOES IN A FILE. This folder is a git repository, so a key written
into a config or a source file would be committed and shared. It is read from
the environment instead:

    PowerShell   $env:DEEPSEEK_API_KEY = "sk-..."
    cmd          set DEEPSEEK_API_KEY=sk-...
    Git Bash     export DEEPSEEK_API_KEY=sk-...
"""

from __future__ import annotations

import os

from autogen_core.models import ModelInfo
from autogen_ext.models.ollama import OllamaChatCompletionClient
from autogen_ext.models.openai import OpenAIChatCompletionClient

PROVIDERS = ("ollama", "deepseek")

# DeepSeek speaks the same shape as the OpenAI API, so the OpenAI client works
# once it is pointed at their address.
DEEPSEEK_URL = "https://api.deepseek.com/v1"
DEEPSEEK_KEY_ENV = "DEEPSEEK_API_KEY"

# A sensible model for each provider, used only when the config does not name
# one. These are the models measured in TEST_REPORT.md.
DEFAULT_MODEL = {
    "ollama": "llama3.1:8b-instruct-q8_0",
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


def deepseek_key() -> str:
    """Read the DeepSeek key from the environment, or stop with instructions.

    We check this BEFORE the run starts. Otherwise the failure arrives after
    the agents are built and the first question is already on screen, which
    looks like a bug in the network rather than a missing key.
    """
    key = os.environ.get(DEEPSEEK_KEY_ENV, "").strip()
    if not key:
        raise SystemExit(
            f"\n{DEEPSEEK_KEY_ENV} is not set, but provider is 'deepseek'.\n\n"
            f"  PowerShell   $env:{DEEPSEEK_KEY_ENV} = \"sk-...\"\n"
            f"  cmd          set {DEEPSEEK_KEY_ENV}=sk-...\n"
            f"  Git Bash     export {DEEPSEEK_KEY_ENV}=sk-...\n\n"
            "Do not put the key in config.yaml - it would be committed to git.\n"
            "To run offline instead, set  provider: \"ollama\"  in the config.")
    return key


def make_client(provider: str, model: str):
    """Build the model client for one provider."""
    if provider == "deepseek":
        return OpenAIChatCompletionClient(
            model=model,
            base_url=DEEPSEEK_URL,
            api_key=deepseek_key(),
            model_info=_PLAIN_TEXT,
        )
    if provider == "ollama":
        # Ollama models are not in AutoGen's built-in list, so we have to say
        # what they can do.
        return OllamaChatCompletionClient(model=model, model_info=_PLAIN_TEXT)
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

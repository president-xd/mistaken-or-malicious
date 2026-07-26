"""Tests for choosing where the model runs.

Two providers: "ollama" on this machine, and "deepseek" over the API. The
things that can go wrong are all about the SWITCH, not about either provider
on its own:

  * switching provider must not carry the old provider's model name across
  * a missing API key must stop the run before any agent is built
  * the default must stay local, so nothing costs money by accident

Run:  python -m unittest discover -s tests
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from p2p import providers
from p2p.config import load_config

CONFIG = """
provider: "ollama"
model: "llama3.1:8b-instruct-q8_0"
agents: 3
rounds: 2
questions:
  - text: "Q1"
    answer: "yes"
"""


def write_config(text=CONFIG):
    """Write a config to a temporary file and give back its path."""
    handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False,
                                         encoding="utf-8")
    handle.write(text)
    handle.close()
    return handle.name


class TestDefaults(unittest.TestCase):

    def test_the_default_provider_is_local(self):
        """Nothing should reach a paid API unless it was asked for."""
        path = write_config("questions:\n  - text: 'Q1'\n")
        try:
            self.assertEqual(load_config(path).provider, "ollama")
        finally:
            os.unlink(path)

    def test_every_provider_has_a_default_model(self):
        for name in providers.PROVIDERS:
            self.assertTrue(providers.DEFAULT_MODEL.get(name),
                            f"{name} has no default model")


class TestSwitchingProvider(unittest.TestCase):
    """The bug this guards against: switching to deepseek on the command line
    while quietly keeping `llama3.1:8b-instruct-q8_0` from the config, then
    sending that name to the API."""

    def setUp(self):
        self.path = write_config()
        self.addCleanup(os.unlink, self.path)

    def test_config_alone_uses_the_config_model(self):
        cfg = load_config(self.path)
        self.assertEqual(cfg.provider, "ollama")
        self.assertEqual(cfg.model, "llama3.1:8b-instruct-q8_0")

    def test_switching_provider_switches_the_model_too(self):
        cfg = load_config(self.path, provider="deepseek")
        self.assertEqual(cfg.provider, "deepseek")
        self.assertEqual(cfg.model, providers.DEFAULT_MODEL["deepseek"])
        self.assertNotIn("llama", cfg.model)

    def test_an_explicit_model_always_wins(self):
        cfg = load_config(self.path, provider="deepseek",
                          model="deepseek-v4-flash")
        self.assertEqual(cfg.model, "deepseek-v4-flash")

    def test_naming_the_same_provider_keeps_the_config_model(self):
        """--provider ollama on an ollama config must change nothing."""
        cfg = load_config(self.path, provider="ollama")
        self.assertEqual(cfg.model, "llama3.1:8b-instruct-q8_0")

    def test_model_alone_does_not_change_the_provider(self):
        cfg = load_config(self.path, model="llama3.2:1b")
        self.assertEqual(cfg.provider, "ollama")
        self.assertEqual(cfg.model, "llama3.2:1b")


class TestBadConfigIsCaughtEarly(unittest.TestCase):

    def test_unknown_provider_is_refused(self):
        path = write_config("provider: 'banana'\nquestions:\n  - text: 'Q1'\n")
        self.addCleanup(os.unlink, path)
        with self.assertRaises(SystemExit) as caught:
            load_config(path)
        self.assertIn("provider", str(caught.exception))

    def test_empty_model_is_refused(self):
        path = write_config("model: ''\nquestions:\n  - text: 'Q1'\n")
        self.addCleanup(os.unlink, path)
        with self.assertRaises(SystemExit):
            load_config(path)


class TestTheKeyIsCheckedBeforeTheRun(unittest.TestCase):
    """A missing key must stop the run at the start, not half way through.

    Otherwise the failure appears after the agents are built and the first
    question is already on screen, which looks like a bug in the network.
    """

    # Both the environment AND the .env file have to be blanked out. Clearing
    # only the environment made these two tests pass or fail depending on
    # whether the developer happened to have a .env file on disk.
    def setUp(self):
        self.no_env_file = mock.patch.object(providers, "read_env_file",
                                             lambda *a: {})
        self.no_env_file.start()
        self.addCleanup(self.no_env_file.stop)

    def test_no_key_stops_with_instructions(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit) as caught:
                providers.check_ready("deepseek")
        message = str(caught.exception)
        self.assertIn("DEEPSEEK_API_KEY", message)
        # It must say how to fix it, not just that it is broken.
        self.assertIn("export", message)

    def test_a_blank_key_counts_as_missing(self):
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "   "}):
            with self.assertRaises(SystemExit):
                providers.check_ready("deepseek")

    def test_a_key_that_is_set_passes(self):
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}):
            self.assertEqual(providers.deepseek_key(), "sk-test")

    def test_ollama_needs_no_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            providers.check_ready("ollama")   # must not raise


class TestReadingTheEnvFile(unittest.TestCase):
    """`.env.example` tells people to put the key in a `.env` file, so that
    file has to actually be read. It is twelve lines of parsing rather than a
    new package, so these tests cover the shapes people really write."""

    def write_env(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".env", delete=False,
                                             encoding="utf-8")
        handle.write(text)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_plain_line(self):
        path = self.write_env("DEEPSEEK_API_KEY=sk-abc123\n")
        self.assertEqual(providers.read_env_file(path),
                         {"DEEPSEEK_API_KEY": "sk-abc123"})

    def test_blank_lines_and_comments_are_skipped(self):
        path = self.write_env("# my key\n\nDEEPSEEK_API_KEY=sk-abc\n\n")
        self.assertEqual(providers.read_env_file(path),
                         {"DEEPSEEK_API_KEY": "sk-abc"})

    def test_quotes_are_stripped(self):
        """People add quotes out of habit; a real key has none."""
        path = self.write_env('DEEPSEEK_API_KEY="sk-abc"\n')
        self.assertEqual(providers.read_env_file(path)["DEEPSEEK_API_KEY"],
                         "sk-abc")

    def test_spaces_around_the_equals_are_ignored(self):
        path = self.write_env("DEEPSEEK_API_KEY = sk-abc \n")
        self.assertEqual(providers.read_env_file(path)["DEEPSEEK_API_KEY"],
                         "sk-abc")

    def test_a_line_with_no_equals_does_not_crash(self):
        """A stray note in the file must not stop a run."""
        path = self.write_env("just a note\nDEEPSEEK_API_KEY=sk-abc\n")
        self.assertEqual(providers.read_env_file(path)["DEEPSEEK_API_KEY"],
                         "sk-abc")

    def test_a_missing_file_is_not_an_error(self):
        self.assertEqual(providers.read_env_file("no_such_file.env"), {})

    def test_no_trailing_newline_still_reads(self):
        """.env.example has no newline at the end of its only line."""
        path = self.write_env("DEEPSEEK_API_KEY=sk-abc")
        self.assertEqual(providers.read_env_file(path)["DEEPSEEK_API_KEY"],
                         "sk-abc")


class TestWhichKeyWins(unittest.TestCase):
    """The shell must beat the file. Otherwise a stale .env quietly overrides
    the key you just exported, and you debug the wrong one."""

    def test_the_environment_beats_the_file(self):
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-from-shell"}), \
             mock.patch.object(providers, "read_env_file",
                               lambda *a: {"DEEPSEEK_API_KEY": "sk-from-file"}):
            self.assertEqual(providers.deepseek_key(), "sk-from-shell")

    def test_the_file_is_used_when_the_shell_has_nothing(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(providers, "read_env_file",
                               lambda *a: {"DEEPSEEK_API_KEY": "sk-from-file"}):
            self.assertEqual(providers.deepseek_key(), "sk-from-file")

    def test_the_example_placeholder_is_refused(self):
        """Catching this here saves a confusing 401 from the API."""
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(
                 providers, "read_env_file",
                 lambda *a: {"DEEPSEEK_API_KEY": "YOUR_API_KEY_GOES_HERE"}):
            with self.assertRaises(SystemExit) as caught:
                providers.deepseek_key()
        self.assertIn("example value", str(caught.exception))

    def test_the_error_names_both_places_to_put_it(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(providers, "read_env_file", lambda *a: {}):
            with self.assertRaises(SystemExit) as caught:
                providers.deepseek_key()
        message = str(caught.exception)
        self.assertIn(".env", message)
        self.assertIn("export", message)


class TestNoKeyEverReachesDisk(unittest.TestCase):
    """The key must come from the environment and nowhere else.

    A key written into config.yaml would be committed to git and shared. This
    checks the config reader has no way to accept one.
    """

    def test_config_has_no_api_key_setting(self):
        from p2p.config import Config
        fields = Config.__dataclass_fields__
        for name in fields:
            self.assertNotIn("key", name.lower(),
                             f"config field {name!r} looks like it holds a key")

    def test_a_key_in_the_config_file_is_ignored(self):
        path = write_config("api_key: 'sk-should-be-ignored'\n"
                            "questions:\n  - text: 'Q1'\n")
        self.addCleanup(os.unlink, path)
        cfg = load_config(path)
        self.assertNotIn("sk-should-be-ignored", str(vars(cfg)))


class TestDescribe(unittest.TestCase):
    """The run header must say where the answers came from, so a saved log
    can never be mistaken for one produced by the other provider."""

    def test_names_the_provider_and_the_model(self):
        line = providers.describe("deepseek", "deepseek-v4-pro")
        self.assertIn("deepseek", line)
        self.assertIn("deepseek-v4-pro", line)

    def test_ollama_line_names_ollama(self):
        self.assertIn("ollama", providers.describe("ollama", "llama3.2:1b"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""A minimal peer-to-peer multi-agent network built on Microsoft AutoGen.

N identical peer agents (named at runtime) each answer a question on their own,
then discuss over a configurable topology (mesh / star / ring / line) and change
their mind when a peer is more convincing. There is no orchestrator agent.
"""

from .config import Config, load_config
from .network import run_network

__all__ = ["Config", "load_config", "run_network"]

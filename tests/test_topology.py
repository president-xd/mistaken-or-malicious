"""In-depth structural tests for every topology.

These are fast, deterministic tests (no model calls): a topology is just a graph,
so we verify its graph properties hold for many agent counts.

Run:  python -m unittest discover -s tests   (from the project root)
"""

import unittest

from p2p import topology
from p2p.agent import agent_names

# The classic topologies (aliases like "point-to-point" resolve to the same graph).
ALL = ["mesh", "bus", "star", "ring", "line", "tree", "hybrid", "p2p"]
SIZES = range(2, 9)


def edges(adj):
    """Set of undirected edges (frozensets) in an adjacency map."""
    return {frozenset((a, b)) for a, nbrs in adj.items() for b in nbrs}


def degree(adj):
    return {n: len(nbrs) for n, nbrs in adj.items()}


def connected(adj):
    """BFS from the first node; is every node reachable?"""
    nodes = list(adj)
    seen, stack = {nodes[0]}, [nodes[0]]
    while stack:
        for nb in adj[stack.pop()]:
            if nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return len(seen) == len(nodes)


class TestUniversalInvariants(unittest.TestCase):
    """Properties that must hold for EVERY topology at EVERY size."""

    def test_keys_are_all_agents(self):
        for kind in ALL:
            for n in SIZES:
                names = agent_names(n)
                adj = topology.build(kind, names)
                self.assertEqual(set(adj), set(names), f"{kind} n={n}")

    def test_no_self_loops(self):
        for kind in ALL:
            for n in SIZES:
                adj = topology.build(kind, agent_names(n))
                for node, nbrs in adj.items():
                    self.assertNotIn(node, nbrs, f"{kind} n={n}: {node} hears itself")

    def test_no_duplicate_neighbours(self):
        for kind in ALL:
            for n in SIZES:
                adj = topology.build(kind, agent_names(n))
                for node, nbrs in adj.items():
                    self.assertEqual(len(nbrs), len(set(nbrs)), f"{kind} n={n}: {node}")

    def test_symmetric(self):
        # All these topologies are undirected: if A hears B, B must hear A.
        for kind in ALL:
            for n in SIZES:
                adj = topology.build(kind, agent_names(n))
                for a, nbrs in adj.items():
                    for b in nbrs:
                        self.assertIn(a, adj[b], f"{kind} n={n}: {a}->{b} not mutual")


class TestPerTopologyShape(unittest.TestCase):
    """The specific shape each topology is supposed to have."""

    def test_mesh_is_complete(self):
        for n in SIZES:
            adj = topology.build("mesh", agent_names(n))
            self.assertTrue(all(d == n - 1 for d in degree(adj).values()))
            self.assertEqual(len(edges(adj)), n * (n - 1) // 2)

    def test_bus_equals_mesh(self):
        # Documented equivalence: a shared bus = everyone hears everyone.
        for n in SIZES:
            names = agent_names(n)
            self.assertEqual(
                topology.build("bus", names), topology.build("mesh", names))

    def test_star_hub_and_spokes(self):
        for n in SIZES:
            names = agent_names(n)
            adj = topology.build("star", names)
            deg = degree(adj)
            self.assertEqual(deg[names[0]], n - 1)                # hub
            self.assertTrue(all(deg[s] == 1 for s in names[1:]))  # spokes
            self.assertEqual(len(edges(adj)), n - 1)

    def test_ring_all_degree_two(self):
        for n in SIZES:
            adj = topology.build("ring", agent_names(n))
            if n == 2:
                self.assertTrue(all(d == 1 for d in degree(adj).values()))
            else:
                self.assertTrue(all(d == 2 for d in degree(adj).values()))
                self.assertEqual(len(edges(adj)), n)

    def test_line_endpoints_degree_one(self):
        for n in SIZES:
            names = agent_names(n)
            adj = topology.build("line", names)
            self.assertEqual(degree(adj)[names[0]], 1)
            self.assertEqual(degree(adj)[names[-1]], 1)
            self.assertEqual(len(edges(adj)), n - 1)

    def test_tree_is_spanning(self):
        # A tree over n nodes has exactly n-1 edges and is connected.
        for n in SIZES:
            adj = topology.build("tree", agent_names(n))
            self.assertEqual(len(edges(adj)), n - 1)
            self.assertTrue(connected(adj))

    def test_hybrid_hub_plus_ring(self):
        for n in SIZES:
            names = agent_names(n)
            adj = topology.build("hybrid", names)
            deg = degree(adj)
            self.assertEqual(deg[names[0]], n - 1)  # hub reaches all
            # each spoke: hub + 2 ring neighbours = degree 3 once there are >=3 spokes
            if n - 1 >= 3:
                self.assertTrue(all(deg[s] == 3 for s in names[1:]))
            self.assertTrue(connected(adj))

    def test_p2p_is_a_matching(self):
        for n in SIZES:
            adj = topology.build("p2p", agent_names(n))
            deg = degree(adj)
            if n % 2 == 0:
                # perfect matching: everyone paired, disconnected for n >= 4
                self.assertTrue(all(d == 1 for d in deg.values()))
                self.assertEqual(len(edges(adj)), n // 2)
                self.assertEqual(connected(adj), n == 2)
            else:
                # one 3-chain: exactly one node of degree 2, rest degree 1
                self.assertEqual(sorted(deg.values()).count(2), 1)

    def test_point_to_point_alias(self):
        for n in SIZES:
            names = agent_names(n)
            self.assertEqual(
                topology.build("point-to-point", names),
                topology.build("p2p", names))


class TestConnectivity(unittest.TestCase):
    """Everything except p2p should keep the whole network reachable."""

    def test_connected(self):
        for kind in ["mesh", "bus", "star", "ring", "line", "tree", "hybrid"]:
            for n in SIZES:
                adj = topology.build(kind, agent_names(n))
                self.assertTrue(connected(adj), f"{kind} n={n} not connected")


class TestErrors(unittest.TestCase):

    def test_too_few_agents(self):
        with self.assertRaises(SystemExit):
            topology.build("mesh", agent_names(1))

    def test_unknown_topology(self):
        with self.assertRaises(KeyError):
            topology.build("banana", agent_names(3))


if __name__ == "__main__":
    unittest.main(verbosity=2)

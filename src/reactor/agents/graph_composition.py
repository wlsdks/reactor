from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from langgraph.graph import END, START, StateGraph


@dataclass(frozen=True)
class GraphNodeSpec:
    name: str
    action: Any


@dataclass(frozen=True)
class GraphStageSpec:
    name: str
    nodes: tuple[GraphNodeSpec, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("graph stage name is required")
        if not self.nodes:
            raise ValueError(f"graph stage {self.name!r} must contain at least one node")


@dataclass(frozen=True)
class GraphSubgraphSpec:
    stage: GraphStageSpec
    compiled: Any
    checkpoint_mode: str = "inherited_parent"

    @property
    def name(self) -> str:
        return self.stage.name

    @property
    def entry_node(self) -> str:
        return self.stage.nodes[0].name

    @property
    def exit_node(self) -> str:
        return self.stage.nodes[-1].name


def graph_stage_order(stages: Sequence[GraphStageSpec]) -> tuple[str, ...]:
    return tuple(stage.name for stage in stages)


def graph_node_order(stages: Sequence[GraphStageSpec]) -> tuple[str, ...]:
    return tuple(node.name for stage in stages for node in stage.nodes)


def subgraph_stage_order(subgraphs: Sequence[GraphSubgraphSpec]) -> tuple[str, ...]:
    return tuple(subgraph.name for subgraph in subgraphs)


def subgraph_edge_order(subgraphs: Sequence[GraphSubgraphSpec]) -> tuple[tuple[str, str], ...]:
    names = subgraph_stage_order(subgraphs)
    if not names:
        raise ValueError("graph must contain at least one subgraph")
    return ((START, names[0]), *pairwise(names), (names[-1], END))


def build_stage_subgraphs(
    stages: Sequence[GraphStageSpec], state_schema: Any
) -> tuple[GraphSubgraphSpec, ...]:
    validate_stage_subgraph_specs(stages)
    return tuple(_build_stage_subgraph(stage, state_schema) for stage in stages)


def validate_stage_subgraph_specs(stages: Sequence[GraphStageSpec]) -> None:
    seen_stages: set[str] = set()
    seen_nodes: set[str] = set()
    for stage in stages:
        if stage.name in seen_stages:
            raise ValueError(f"duplicate graph stage {stage.name!r}")
        seen_stages.add(stage.name)
        for node in stage.nodes:
            if node.name in seen_nodes:
                raise ValueError(f"duplicate graph node {node.name!r}")
            seen_nodes.add(node.name)


def _build_stage_subgraph(stage: GraphStageSpec, state_schema: Any) -> GraphSubgraphSpec:
    graph = StateGraph(state_schema)
    for node in stage.nodes:
        graph.add_node(node.name, node.action)
    graph.add_edge(START, stage.nodes[0].name)
    for source, target in pairwise(node.name for node in stage.nodes):
        graph.add_edge(source, target)
    graph.add_edge(stage.nodes[-1].name, END)
    return GraphSubgraphSpec(stage=stage, compiled=graph.compile())


def add_stage_nodes(graph: StateGraph[Any], stages: Sequence[GraphStageSpec]) -> None:
    seen: set[str] = set()
    for stage in stages:
        for node in stage.nodes:
            if node.name in seen:
                raise ValueError(f"duplicate graph node {node.name!r}")
            seen.add(node.name)
            graph.add_node(node.name, node.action)


def add_linear_stage_edges(graph: StateGraph[Any], stages: Sequence[GraphStageSpec]) -> None:
    nodes = graph_node_order(stages)
    if not nodes:
        raise ValueError("graph must contain at least one node")
    graph.add_edge(START, nodes[0])
    for source, target in pairwise(nodes):
        graph.add_edge(source, target)
    graph.add_edge(nodes[-1], END)


def add_subgraph_nodes(graph: StateGraph[Any], subgraphs: Sequence[GraphSubgraphSpec]) -> None:
    seen: set[str] = set()
    for subgraph in subgraphs:
        if subgraph.name in seen:
            raise ValueError(f"duplicate graph subgraph {subgraph.name!r}")
        seen.add(subgraph.name)
        graph.add_node(subgraph.name, subgraph.compiled)


def add_linear_subgraph_edges(
    graph: StateGraph[Any], subgraphs: Sequence[GraphSubgraphSpec]
) -> None:
    for source, target in subgraph_edge_order(subgraphs):
        graph.add_edge(source, target)

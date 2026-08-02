from __future__ import annotations

from dataclasses import asdict, dataclass, field
from heapq import heappop, heappush
from math import inf


@dataclass(slots=True)
class Region:
    id: str
    name_pt_br: str
    name_en_us: str
    aliases: list[str] = field(default_factory=list)
    confidence: float = 1.0
    exploration_status: str = "unknown"


@dataclass(slots=True)
class RegionConnection:
    source: str
    destination: str
    cost: float = 1.0
    reliability: float = 1.0
    exit_id: str | None = None
    entry_id: str | None = None
    bidirectional: bool = True


class WorldGraph:
    def __init__(self) -> None:
        self.regions: dict[str, Region] = {}
        self.connections: list[RegionConnection] = []

    def add_region(self, region: Region) -> None:
        self.regions[region.id] = region

    def connect(self, connection: RegionConnection) -> None:
        if connection.source not in self.regions or connection.destination not in self.regions:
            raise KeyError("Both regions must exist before connecting them")
        self.connections.append(connection)

    def route(self, source: str, destination: str) -> list[str]:
        if source not in self.regions or destination not in self.regions:
            return []
        adjacency: dict[str, list[tuple[str, float]]] = {region_id: [] for region_id in self.regions}
        for edge in self.connections:
            penalty = edge.cost / max(edge.reliability, 0.05)
            adjacency[edge.source].append((edge.destination, penalty))
            if edge.bidirectional:
                adjacency[edge.destination].append((edge.source, penalty))
        queue: list[tuple[float, str]] = [(0.0, source)]
        distances = {region_id: inf for region_id in self.regions}
        previous: dict[str, str] = {}
        distances[source] = 0.0
        while queue:
            current_cost, current = heappop(queue)
            if current == destination:
                break
            if current_cost > distances[current]:
                continue
            for neighbor, weight in adjacency[current]:
                candidate = current_cost + weight
                if candidate < distances[neighbor]:
                    distances[neighbor] = candidate
                    previous[neighbor] = current
                    heappush(queue, (candidate, neighbor))
        if distances[destination] == inf:
            return []
        path = [destination]
        while path[-1] != source:
            path.append(previous[path[-1]])
        return list(reversed(path))

    def to_dict(self) -> dict:
        return {
            "regions": [asdict(region) for region in self.regions.values()],
            "connections": [asdict(connection) for connection in self.connections],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "WorldGraph":
        graph = cls()
        for item in payload.get("regions", []):
            graph.add_region(Region(**item))
        for item in payload.get("connections", []):
            graph.connect(RegionConnection(**item))
        return graph

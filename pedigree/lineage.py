"""Model lineage from Hugging Face tags.

The Hub tags every model whose card names a base model: `base_model:<id>` for any relation, and
`base_model:<relation>:<id>` with relation finetune, adapter, merge or quantized. Licences are tagged `license:<id>`.
This module turns rows of (model id, tags) into parents, relations and declared licences. It is pure: no network.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

RELATIONS = ("finetune", "adapter", "merge", "quantized")


@dataclass
class Model:
    id: str
    licence: str | None = None
    parents: dict[str, str] = field(default_factory=dict)  # parent id -> relation
    downloads: int = 0
    likes: int = 0
    created: str = ""
    library: str = ""
    pipeline: str = ""

    @property
    def author(self) -> str:
        return self.id.split("/", 1)[0] if "/" in self.id else ""

    @property
    def name(self) -> str:
        return self.id.split("/", 1)[-1]


@dataclass
class Parsed:
    models: dict[str, Model]
    self_loops: int = 0
    unknown_parents: int = 0


def parse_tags(model_id: str, tags: Iterable[str]) -> tuple[str | None, dict[str, str], bool]:
    """The declared licence, the parents (id -> relation) and whether the card names the model as its own base."""
    licence: str | None = None
    typed: dict[str, str] = {}
    untyped: list[str] = []
    for tag in tags:
        if tag.startswith("license:"):
            licence = licence or tag.split(":", 1)[1]
        elif tag.startswith("base_model:"):
            rest = tag.split(":", 1)[1]
            head, _, tail = rest.partition(":")
            if head in RELATIONS and tail:
                typed[tail] = head
            else:
                untyped.append(rest)
    parents = dict(typed)
    for parent in untyped:
        parents.setdefault(parent, "base")
    self_loop = parents.pop(model_id, None) is not None  # a few cards name the model itself as its base
    return licence, parents, self_loop


def parse_rows(rows: Iterable[Mapping[str, object]]) -> Parsed:
    """Rows with modelId and tags (and optional downloads, likes, createdAt, library_name, pipeline_tag)."""
    models: dict[str, Model] = {}
    loops = 0
    for row in rows:
        model_id = str(row["modelId"])
        raw_tags = row.get("tags") or []
        tags = [str(t) for t in raw_tags] if isinstance(raw_tags, list | tuple) else []
        licence, parents, self_loop = parse_tags(model_id, tags)
        loops += self_loop
        models[model_id] = Model(
            id=model_id,
            licence=licence,
            parents=parents,
            downloads=int(row.get("downloads") or 0),  # type: ignore[call-overload]
            likes=int(row.get("likes") or 0),  # type: ignore[call-overload]
            created=str(row.get("createdAt") or ""),
            library=str(row.get("library_name") or ""),
            pipeline=str(row.get("pipeline_tag") or ""),
        )
    # Ids are case-sensitive on the Hub, but a card can name a parent with other casing: resolve it when unambiguous.
    by_lower: dict[str, list[str]] = defaultdict(list)
    for model_id in models:
        by_lower[model_id.lower()].append(model_id)
    unknown = 0
    for model in models.values():
        resolved: dict[str, str] = {}
        for parent, relation in model.parents.items():
            if parent in models:
                resolved[parent] = relation
            elif len(by_lower.get(parent.lower(), [])) == 1:
                resolved[by_lower[parent.lower()][0]] = relation
            else:
                unknown += 1
                resolved[parent] = relation  # kept: a parent outside the snapshot is still a parent
        model.parents = resolved
    return Parsed(models=models, self_loops=loops, unknown_parents=unknown)


def descendants(models: Mapping[str, Model], roots: Iterable[str]) -> set[str]:
    """Every model that derives, directly or not, from one of the roots (the roots included)."""
    children: dict[str, list[str]] = defaultdict(list)
    for model in models.values():
        for parent in model.parents:
            children[parent].append(model.id)
    seen: set[str] = set()
    queue = deque(r for r in roots)
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(c for c in children.get(current, []) if c not in seen)
    return seen


def family_roots(models: Mapping[str, Model], owners: Iterable[str]) -> list[str]:
    """Models published by the given owners (for example meta-llama, google): the roots of the families."""
    wanted = {o.lower() for o in owners}
    return sorted(m.id for m in models.values() if m.author.lower() in wanted)

from pathlib import Path

import yaml

from app.sources.eis import EisRssSource
from app.sources.fl_ru import FlRssSource
from app.sources.generic import GenericRssSource, ManualSource
from app.sources.habr_career import HabrCareerSource
from app.sources.workspace import WorkspaceCatalogSource

KINDS = {
    "fl_rss": FlRssSource,
    "habr_rss": HabrCareerSource,
    "workspace_catalog": WorkspaceCatalogSource,
    "eis_rss": EisRssSource,
    "rss_generic": GenericRssSource,
    "manual": ManualSource,
}


def load_source_specs(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("sources") or []


def build_sources(specs: list[dict]) -> list:
    built = []
    for spec in specs:
        kind = spec.get("kind")
        if kind not in KINDS:
            raise ValueError(f"unknown source kind {kind} for {spec.get('id')}")
        if not spec.get("enabled", False):
            built.append(ManualSource(spec))
            continue
        built.append(KINDS[kind](spec))
    return built

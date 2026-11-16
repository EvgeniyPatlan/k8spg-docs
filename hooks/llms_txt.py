"""MkDocs hook for the mkdocs-llmstxt plugin.

It does two things the plugin can't do from mkdocs.yml alone:

* Builds the plugin's ``sections`` from ``nav``, so llms.txt follows the
  navigation and there is no second list of pages to keep in sync. Each
  top-level nav group becomes a ``## section``; top-level pages go into the
  first section.
* Starts the markdown version of every page with a pointer to this site's
  llms.txt, so an agent that lands on one page can find the whole index.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.plugins import BasePlugin, event_priority
from mkdocs.structure.files import Files

PLUGIN = "llmstxt"
FIRST_SECTION = "Overview"

# Markdown pages written by the plugin, as paths relative to site_dir.
_md_pages: list[str] = []


def nav_pages(item: Any) -> list[str]:
    """Return the ``.md`` files in a nav item, in nav order. Links are skipped."""
    if isinstance(item, str):
        return [item] if item.endswith(".md") else []
    if isinstance(item, dict):
        return [page for value in item.values() for page in nav_pages(value)]
    if isinstance(item, list):
        return [page for value in item for page in nav_pages(value)]
    return []


def sections_from_nav(nav: list[Any]) -> dict[str, list[str]]:
    """Map each top-level nav group to its pages; loose pages go first."""
    sections: dict[str, list[str]] = {FIRST_SECTION: []}
    for item in nav:
        if isinstance(item, dict) and len(item) == 1:
            title, value = next(iter(item.items()))
            if isinstance(value, list):
                sections.setdefault(title, []).extend(nav_pages(value))
                continue
        sections[FIRST_SECTION].extend(nav_pages(item))
    return {title: list(dict.fromkeys(pages)) for title, pages in sections.items() if pages}


def directive(index_url: str) -> str:
    """The line that starts every markdown page."""
    return f"> For the complete documentation index, see [llms.txt]({index_url}).\n\n"


def _plugin(config: MkDocsConfig) -> BasePlugin[Any] | None:
    plugin: BasePlugin[Any] | None = config.plugins.get(PLUGIN)
    return plugin


def on_config(config: MkDocsConfig) -> MkDocsConfig:
    """Fill the plugin's sections from nav, unless mkdocs.yml lists them."""
    plugin = _plugin(config)
    if plugin is not None and not plugin.config.sections:
        plugin.config.sections = sections_from_nav(config.nav or [])
    return config


def on_files(files: Files, *, config: MkDocsConfig) -> Files:
    """Remember where the plugin will write the markdown pages."""
    plugin = _plugin(config)
    _md_pages.clear()
    if plugin is not None:
        wanted = {page for pages in plugin.config.sections.values() for page in pages}
        _md_pages.extend(
            Path(file.dest_uri).with_suffix(".md").as_posix()
            for file in files.documentation_pages()
            if file.src_uri in wanted
        )
    return files


@event_priority(-100)  # after the plugin has written the markdown pages
def on_post_build(*, config: MkDocsConfig) -> None:
    """Prepend the pointer to llms.txt to every markdown page."""
    plugin = _plugin(config)
    if plugin is None:
        return
    base_url = plugin.config.base_url or config.site_url or "/"
    line = directive(base_url.rstrip("/") + "/llms.txt")
    site_dir = Path(config.site_dir)
    for name in _md_pages:
        path = site_dir / name
        if path.is_file():
            path.write_text(line + path.read_text(encoding="utf-8"), encoding="utf-8")

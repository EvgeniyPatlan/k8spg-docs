"""Tests for hooks/llms_txt.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from mkdocs.commands.build import build
from mkdocs.config import load_config

import llms_txt

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "llms_txt.py"
INDEX_URL = "https://docs.example.com/product/latest/llms.txt"


# --- nav_pages ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ("page.md", ["page.md"]),
        ("https://example.com/", []),
        ({"Title": "page.md"}, ["page.md"]),
        ({"Old releases": "https://example.com/"}, []),
        (["a.md", {"B": "b.md"}, {"Group": ["c.md", {"Sub": [{"D": "d.md"}]}]}], ["a.md", "b.md", "c.md", "d.md"]),
        (None, []),
        (42, []),
    ],
)
def test_nav_pages(item: Any, expected: list[str]) -> None:
    assert llms_txt.nav_pages(item) == expected


# --- sections_from_nav -------------------------------------------------------


def test_sections_follow_top_level_groups_and_loose_pages_come_first() -> None:
    nav: list[Any] = [
        {"Home": "index.md"},
        {"Install": ["install.md", {"On Kubernetes": [{"GKE": "gke.md"}]}]},
        "get-help.md",
        {"Reference": ["options.md"]},
        {"Archive": "https://example.com/archive/"},
    ]
    assert llms_txt.sections_from_nav(nav) == {
        "Overview": ["index.md", "get-help.md"],
        "Install": ["install.md", "gke.md"],
        "Reference": ["options.md"],
    }


def test_sections_drop_duplicates_and_empty_groups() -> None:
    nav: list[Any] = [
        {"Guide": ["a.md", "b.md", "a.md"]},
        {"Links": ["https://example.com/"]},
        {"Guide": ["c.md"]},
    ]
    assert llms_txt.sections_from_nav(nav) == {"Guide": ["a.md", "b.md", "c.md"]}


def test_sections_from_empty_nav() -> None:
    assert llms_txt.sections_from_nav([]) == {}


def test_directive() -> None:
    assert llms_txt.directive(INDEX_URL) == f"> For the complete documentation index, see [llms.txt]({INDEX_URL}).\n\n"


def test_mark_human_only() -> None:
    html = (
        '<h2 id="a">A<a class="headerlink" href="#a">¶</a></h2>'
        '<div class="tabbed-labels"><label>X</label></div>'
        '<a class="headerlinks" href="#">kept</a><div class="tabbed-content"></div>'
    )
    assert llms_txt.mark_human_only(html) == (
        '<h2 id="a">A<a data-markdown-ignore class="headerlink" href="#a">¶</a></h2>'
        '<div data-markdown-ignore class="tabbed-labels"><label>X</label></div>'
        '<a class="headerlinks" href="#">kept</a><div class="tabbed-content"></div>'
    )


# --- a real build ------------------------------------------------------------


def make_site(tmp_path: Path, *, sections: str = "{}", plugin: bool = True) -> Path:
    """Write a small MkDocs project that uses the hook, and return its config file."""
    docs = tmp_path / "docs"
    (docs / "notes").mkdir(parents=True)
    (docs / "index.md").write_text("# Home\n\nWelcome.\n", encoding="utf-8")
    (docs / "install.md").write_text("# Install\n\nRun it.\n", encoding="utf-8")
    (docs / "notes" / "1.0.md").write_text("# Release 1.0\n\nFirst.\n", encoding="utf-8")
    (docs / "draft.md").write_text("# Draft\n\nNot in nav.\n", encoding="utf-8")
    plugins = (
        f"""
plugins:
  - llmstxt:
      base_url: https://docs.example.com/product/latest/
      full_output: llms-full.txt
      sections: {sections}
"""
        if plugin
        else "plugins: []\n"
    )
    config = tmp_path / "mkdocs.yml"
    config.write_text(
        f"""
site_name: Product
site_url: https://docs.example.com/product/
use_directory_urls: false
markdown_extensions:
  - toc:
      permalink: true
hooks:
  - {HOOK.as_posix()}
nav:
  - Home: index.md
  - Guide:
      - Install: install.md
  - Release notes:
      - notes/1.0.md
  - Archive: https://example.com/archive/
{plugins}
""",
        encoding="utf-8",
    )
    return config


def run_build(config_file: Path) -> Path:
    config = load_config(str(config_file))
    build(config)
    return Path(config.site_dir)


def test_pages_the_plugin_did_not_write_are_skipped(tmp_path: Path) -> None:
    config = load_config(str(make_site(tmp_path)))
    build(config)
    llms_txt._md_pages.append("gone.md")
    llms_txt.on_post_build(config=config)
    assert not (Path(config.site_dir) / "gone.md").exists()


def test_build_writes_index_from_nav_and_markdown_pages_with_pointer(tmp_path: Path) -> None:
    site = run_build(make_site(tmp_path))

    index = (site / "llms.txt").read_text(encoding="utf-8")
    assert "## Overview\n\n- [Home](https://docs.example.com/product/latest/index.md)" in index
    assert "## Guide\n\n- [Install](https://docs.example.com/product/latest/install.md)" in index
    assert "## Release notes\n\n- [Release 1.0](https://docs.example.com/product/latest/notes/1.0.md)" in index
    assert "Draft" not in index
    assert "Archive" not in index

    for page in ("index.md", "install.md", "notes/1.0.md"):
        text = (site / page).read_text(encoding="utf-8")
        assert text.startswith(llms_txt.directive(INDEX_URL)), page
        assert text.count("For the complete documentation index") == 1, page
    assert not (site / "draft.md").exists()
    assert (site / "llms-full.txt").is_file()
    assert '<a data-markdown-ignore class="headerlink"' in (site / "install.html").read_text(encoding="utf-8")


def test_sections_in_mkdocs_yml_win_over_nav(tmp_path: Path) -> None:
    site = run_build(make_site(tmp_path, sections='{"Only": ["install.md"]}'))
    index = (site / "llms.txt").read_text(encoding="utf-8")
    assert "## Only\n\n- [Install]" in index
    assert "## Overview" not in index
    assert (site / "install.md").read_text(encoding="utf-8").startswith("> ")
    assert not (site / "index.md").exists()


def test_without_the_plugin_the_hook_does_nothing(tmp_path: Path) -> None:
    site = run_build(make_site(tmp_path, plugin=False))
    assert not (site / "llms.txt").exists()
    assert not list(site.rglob("*.md"))
    assert "data-markdown-ignore" not in (site / "install.html").read_text(encoding="utf-8")


def test_pointer_falls_back_to_site_url_without_base_url(tmp_path: Path) -> None:
    config_file = make_site(tmp_path)
    text = config_file.read_text(encoding="utf-8").replace(
        "      base_url: https://docs.example.com/product/latest/\n", ""
    )
    config_file.write_text(text, encoding="utf-8")
    site = run_build(config_file)
    expected = llms_txt.directive("https://docs.example.com/product/llms.txt")
    assert (site / "install.md").read_text(encoding="utf-8").startswith(expected)

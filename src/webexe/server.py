import json
import re
from typing import Literal

from bs4 import BeautifulSoup
from mcp.server.mcpserver import MCPServer

from webexe.scraper import (
    convert_to_markdown,
    convert_to_text,
    extract_links,
    extract_tables,
    extract_title_and_meta,
    fetch_html_browser,
    fetch_html_fast,
)
from webexe.search import search_web_unified

server = MCPServer(
    name="webexe",
    instructions="Web page fetching and information extraction MCP tool. Provides both fast HTTP request mode and headless browser mode.",
)


async def _get_page_html(
    url: str,
    mode: Literal["fast", "browser"],
    wait_for_selector: str | None = None,
    timeout: float = 30.0,
) -> tuple[str, str, int]:
    """Helper to fetch HTML based on the specified mode."""
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url

    if mode == "browser":
        return await fetch_html_browser(
            url=url, wait_for_selector=wait_for_selector, timeout=timeout
        )
    else:
        return await fetch_html_fast(url=url, timeout=timeout)


@server.tool()
async def fetch_web_page(
    url: str,
    mode: Literal["fast", "browser"] = "fast",
    output_format: Literal["markdown", "text", "html"] = "markdown",
    selector: str | None = None,
    wait_for_selector: str | None = None,
    timeout: float = 30.0,
    max_length: int = 50000,
) -> str:
    """Fetch content from a web page and convert it into markdown, plain text, or HTML.

    Args:
        url: The URL of the web page to fetch.
        mode: 'fast' uses lightweight HTTP request (httpx), 'browser' uses headless Chromium (Playwright) for JS rendering/SPA.
        output_format: Output format ('markdown', 'text', or 'html'). Default is 'markdown'.
        selector: Optional CSS selector to extract specific elements (e.g. 'article', '#content', '.main').
        wait_for_selector: Optional CSS selector to wait for before extracting content (only used in 'browser' mode).
        timeout: Timeout in seconds (default: 30.0).
        max_length: Maximum character length of the returned content to prevent token overflow (default: 50000).

    Returns:
        A formatted string containing page metadata (title, status, URL) and extracted content.
    """
    try:
        html, final_url, status_code = await _get_page_html(
            url=url,
            mode=mode,
            wait_for_selector=wait_for_selector,
            timeout=timeout,
        )

        soup = BeautifulSoup(html, "html.parser")
        meta = extract_title_and_meta(soup)

        if output_format == "markdown":
            content = convert_to_markdown(html, selector=selector)
        elif output_format == "text":
            content = convert_to_text(html, selector=selector)
        elif output_format == "html":
            if selector:
                elem = soup.select_one(selector)
                content = str(elem) if elem else f"Selector '{selector}' not found."
            else:
                content = html
        else:
            content = convert_to_markdown(html, selector=selector)

        truncated = False
        original_length = len(content)
        if original_length > max_length:
            content = content[:max_length]
            truncated = True

        result_lines = [
            f"# {meta.get('title') or 'No Title'}",
            f"- **URL**: {final_url}",
            f"- **Status Code**: {status_code}",
            f"- **Fetch Mode**: {mode}",
        ]
        if meta.get("description"):
            result_lines.append(f"- **Description**: {meta['description']}")
        if selector:
            result_lines.append(f"- **Selector**: `{selector}`")
        if truncated:
            result_lines.append(
                f"- **Note**: Content was truncated from {original_length} characters to {max_length} characters."
            )

        result_lines.append("\n---\n")
        result_lines.append(content)

        return "\n".join(result_lines)
    except Exception as e:
        return f"Error fetching web page '{url}': {type(e).__name__}: {str(e)}"


@server.tool()
async def extract_page_links(
    url: str,
    mode: Literal["fast", "browser"] = "fast",
    internal_only: bool = False,
    max_links: int = 100,
    timeout: float = 30.0,
) -> str:
    """Extract links (hyperlinks and anchor text) from a web page.

    Args:
        url: The URL of the web page.
        mode: 'fast' (lightweight HTTP) or 'browser' (headless browser).
        internal_only: If True, only returns links belonging to the same domain.
        max_links: Maximum number of links to return (default: 100).
        timeout: Timeout in seconds.

    Returns:
        Markdown-formatted list of discovered links.
    """
    try:
        html, final_url, status_code = await _get_page_html(
            url=url, mode=mode, timeout=timeout
        )
        links = extract_links(
            html,
            base_url=final_url,
            internal_only=internal_only,
            max_links=max_links,
        )

        lines = [
            f"# Links from {final_url}",
            f"- Total extracted: {len(links)}",
            f"- Filter: {'Internal only' if internal_only else 'All links'}",
            "\n",
        ]
        for item in links:
            text = item["text"] or "(no text)"
            lines.append(f"- [{text}]({item['url']})")

        return "\n".join(lines)
    except Exception as e:
        return f"Error extracting links from '{url}': {type(e).__name__}: {str(e)}"


@server.tool()
async def extract_page_tables(
    url: str,
    mode: Literal["fast", "browser"] = "fast",
    selector: str | None = None,
    table_index: int | None = None,
    timeout: float = 30.0,
) -> str:
    """Extract HTML tables from a web page and convert them to Markdown tables.

    Args:
        url: The URL of the web page.
        mode: 'fast' (lightweight HTTP) or 'browser' (headless browser).
        selector: Optional CSS selector to look for tables inside a specific container.
        table_index: Optional 0-based index if multiple tables exist.
        timeout: Timeout in seconds.

    Returns:
        Markdown tables extracted from the page.
    """
    try:
        html, final_url, status_code = await _get_page_html(
            url=url, mode=mode, timeout=timeout
        )
        tables = extract_tables(
            html, selector=selector, table_index=table_index
        )

        if not tables:
            return f"No tables found on {final_url}"

        output = [f"# Tables extracted from {final_url}\n"]
        for tbl in tables:
            output.append(
                f"### Table #{tbl['table_index'] + 1} ({tbl['row_count']} rows)"
            )
            output.append(tbl["markdown"])
            output.append("\n")

        return "\n".join(output)
    except Exception as e:
        return f"Error extracting tables from '{url}': {type(e).__name__}: {str(e)}"


@server.tool()
async def search_page_content(
    url: str,
    query: str,
    mode: Literal["fast", "browser"] = "fast",
    context_window: int = 150,
    max_results: int = 5,
    timeout: float = 30.0,
) -> str:
    """Search for specific keywords or phrases in a web page and extract surrounding contexts.

    Args:
        url: The URL of the web page.
        query: The keyword or phrase to search for (case-insensitive).
        mode: 'fast' (lightweight HTTP) or 'browser' (headless browser).
        context_window: Number of surrounding characters to include for context (default: 150).
        max_results: Maximum number of match snippets to return (default: 5).
        timeout: Timeout in seconds.

    Returns:
        Search results with contextual snippets.
    """
    try:
        html, final_url, status_code = await _get_page_html(
            url=url, mode=mode, timeout=timeout
        )
        text = convert_to_text(html)

        matches = [m.start() for m in re.finditer(re.escape(query), text, re.IGNORECASE)]

        if not matches:
            return f"Keyword '{query}' was not found in {final_url}."

        snippets = []
        for idx, match_pos in enumerate(matches[:max_results]):
            start = max(0, match_pos - context_window)
            end = min(len(text), match_pos + len(query) + context_window)
            snippet = text[start:end].replace("\n", " ").strip()
            snippets.append(
                f"**Match #{idx + 1}:**\n> ...{snippet}...\n"
            )

        output = [
            f"# Search Results for `{query}` on {final_url}",
            f"- Total matches found: {len(matches)} (showing top {min(len(matches), max_results)})",
            "\n",
            "\n".join(snippets),
        ]
        return "\n".join(output)
    except Exception as e:
        return f"Error searching in page '{url}': {type(e).__name__}: {str(e)}"


@server.tool()
async def search_web(
    query: str,
    engine: Literal["google", "duckduckgo"] = "google",
    max_results: int = 10,
    fallback_to_duckduckgo: bool = True,
    timeout: float = 30.0,
) -> str:
    """Search the web using Google (by accessing google.com, typing query, and parsing results) or DuckDuckGo.

    Args:
        query: The search query / keywords.
        engine: 'google' (launches headless browser, enters query into google.com search box) or 'duckduckgo' (fast direct search). Default is 'google'.
        max_results: Maximum number of search results to return (default: 10).
        fallback_to_duckduckgo: If Google encounters a CAPTCHA or blocking, automatically fallback to DuckDuckGo (default: True).
        timeout: Timeout in seconds.

    Returns:
        Markdown-formatted list of search results including title, URL, and snippet.
    """
    try:
        data = await search_web_unified(
            query=query,
            engine=engine,
            fallback_to_duckduckgo=fallback_to_duckduckgo,
            max_results=max_results,
            timeout=timeout,
        )

        results = data.get("results", [])
        used_engine = data.get("engine", engine)
        note = data.get("note")

        lines = [
            f"# Web Search Results for `{query}`",
            f"- **Engine**: {used_engine.capitalize()}",
            f"- **Results count**: {len(results)}",
        ]
        if note:
            lines.append(f"- **Note**: {note}")
        lines.append("\n---\n")

        if not results:
            lines.append("No search results found.")
            return "\n".join(lines)

        for i, item in enumerate(results, 1):
            title = item.get("title") or "Untitled"
            url = item.get("url") or item.get("display_url") or "#"
            snippet = item.get("snippet") or ""

            lines.append(f"### {i}. [{title}]({url})")
            if item.get("display_url") and item.get("display_url") != url:
                lines.append(f"> Source: `{item['display_url']}`")
            if snippet:
                lines.append(f"\n{snippet}\n")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return f"Error searching the web for '{query}': {type(e).__name__}: {str(e)}"

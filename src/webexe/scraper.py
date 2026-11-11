import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import httpx
from markdownify import markdownify as md
from playwright.async_api import async_playwright

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Tags typically not useful for content extraction
STRIP_TAGS = ["script", "style", "noscript", "svg", "canvas", "iframe"]


async def fetch_html_fast(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> tuple[str, str, int]:
    """Fetch HTML using httpx (fast, lightweight, handles static/SSR pages).

    Returns:
        tuple[html_content, final_url, status_code]
    """
    req_headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"}
    if headers:
        req_headers.update(headers)

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        verify=False,  # avoid cert failures on some internal/self-signed sites
    ) as client:
        resp = await client.get(url, headers=req_headers)
        resp.raise_for_status()
        return resp.text, str(resp.url), resp.status_code


async def fetch_html_browser(
    url: str,
    wait_for_selector: str | None = None,
    timeout: float = 30.0,
) -> tuple[str, str, int]:
    """Fetch HTML using headless Chromium via Playwright (executes JavaScript/SPA).

    Returns:
        tuple[html_content, final_url, status_code]
    """
    timeout_ms = int(timeout * 1000)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                viewport={"width": 1280, "height": 800},
                locale="ja-JP",
            )
            page = await context.new_page()
            response = await page.goto(
                url, wait_until="networkidle", timeout=timeout_ms
            )
            if wait_for_selector:
                await page.wait_for_selector(wait_for_selector, timeout=timeout_ms)

            status_code = response.status if response else 200
            content = await page.content()
            final_url = page.url
            return content, final_url, status_code
        finally:
            await browser.close()


def clean_soup(soup: BeautifulSoup) -> BeautifulSoup:
    """Remove unnecessary elements like scripts, styles, etc."""
    for tag in soup(STRIP_TAGS):
        tag.decompose()
    return soup


def extract_title_and_meta(soup: BeautifulSoup) -> dict[str, str]:
    """Extract page title and meta description."""
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    desc = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else ""
    return {"title": title, "description": desc}


def convert_to_markdown(html_content: str, selector: str | None = None) -> str:
    """Convert HTML content to clean Markdown."""
    soup = BeautifulSoup(html_content, "html.parser")
    clean_soup(soup)

    if selector:
        target = soup.select_one(selector)
        if not target:
            return f"Error: CSS selector '{selector}' was not found in the page."
        target_html = str(target)
    else:
        # If body exists, use body
        target = soup.body or soup
        target_html = str(target)

    text_md = md(target_html, heading_style="ATX", strip=["img"])
    # Clean excessive blank lines
    text_md = re.sub(r"\n{3,}", "\n\n", text_md).strip()
    return text_md


def convert_to_text(html_content: str, selector: str | None = None) -> str:
    """Extract plain text from HTML content."""
    soup = BeautifulSoup(html_content, "html.parser")
    clean_soup(soup)

    if selector:
        target = soup.select_one(selector)
        if not target:
            return f"Error: CSS selector '{selector}' was not found in the page."
        raw_text = target.get_text(separator="\n", strip=True)
    else:
        raw_text = soup.get_text(separator="\n", strip=True)

    # Clean excessive blank lines
    cleaned_text = re.sub(r"\n{3,}", "\n\n", raw_text).strip()
    return cleaned_text


def extract_links(
    html_content: str,
    base_url: str,
    internal_only: bool = False,
    max_links: int = 100,
) -> list[dict[str, str]]:
    """Extract links from HTML content."""
    soup = BeautifulSoup(html_content, "html.parser")
    clean_soup(soup)
    base_domain = urlparse(base_url).netloc

    links: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        absolute_url = urljoin(base_url, href)
        parsed_url = urlparse(absolute_url)

        if internal_only and parsed_url.netloc != base_domain:
            continue

        if absolute_url in seen_urls:
            continue

        seen_urls.add(absolute_url)
        anchor_text = a.get_text(strip=True)
        links.append({"text": anchor_text, "url": absolute_url})

        if len(links) >= max_links:
            break

    return links


def extract_tables(
    html_content: str,
    selector: str | None = None,
    table_index: int | None = None,
) -> list[dict[str, Any]]:
    """Extract HTML tables as structured markdown representations."""
    soup = BeautifulSoup(html_content, "html.parser")
    clean_soup(soup)

    if selector:
        root = soup.select_one(selector) or soup
    else:
        root = soup

    tables = root.find_all("table")
    if not tables:
        return []

    target_tables = [tables[table_index]] if table_index is not None and 0 <= table_index < len(tables) else tables

    results: list[dict[str, Any]] = []
    for idx, tbl in enumerate(target_tables):
        actual_idx = table_index if table_index is not None else idx
        # Extract rows
        rows_data: list[list[str]] = []
        for tr in tbl.find_all("tr"):
            cells = [cell.get_text(strip=True).replace("\n", " ") for cell in tr.find_all(["th", "td"])]
            if cells:
                rows_data.append(cells)

        if not rows_data:
            continue

        # Format as Markdown table
        header = rows_data[0]
        md_table_lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(["---"] * len(header)) + " |",
        ]
        for row in rows_data[1:]:
            # Pad row if columns don't match header
            padded_row = row + [""] * (len(header) - len(row))
            md_table_lines.append("| " + " | ".join(padded_row[:len(header)]) + " |")

        results.append({
            "table_index": actual_idx,
            "row_count": len(rows_data),
            "markdown": "\n".join(md_table_lines),
        })

    return results

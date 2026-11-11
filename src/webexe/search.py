import asyncio
import re
from typing import Any, Literal
from urllib.parse import unquote

from bs4 import BeautifulSoup
import httpx
from playwright.async_api import async_playwright

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


def _clean_cite_url(cite_text: str) -> str:
    """Format cite text like 'https://example.com › path' into a clean URL."""
    if not cite_text:
        return ""
    # Replace arrow markers
    cleaned = cite_text.replace("›", "/").replace(">", "/").replace(" ", "")
    # Add https:// if missing
    if not cleaned.startswith("http://") and not cleaned.startswith("https://"):
        cleaned = "https://" + cleaned
    return cleaned


async def search_google_browser(
    query: str,
    max_results: int = 10,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Search Google by visiting google.com, typing query into search box, and parsing results.

    Returns:
        dict containing 'status', 'engine', 'results': list of {title, url, display_url, snippet}
    """
    timeout_ms = int(timeout * 1000)
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        try:
            context = await browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                viewport={"width": 1280, "height": 800},
                locale="ja-JP",
            )
            # Remove navigator.webdriver detection
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            page = await context.new_page()

            # 1. Navigate to Google Japan
            await page.goto(
                "https://www.google.co.jp/",
                wait_until="domcontentloaded",
                timeout=timeout_ms,
            )

            # 2. Locate search input and fill query
            search_box = page.locator('textarea[name="q"], input[name="q"]').first
            if await search_box.count() == 0:
                title = await page.title()
                content = await page.content()
                if "captcha" in content.lower() or "通常と異なるトラフィック" in content:
                    return {
                        "status": "blocked",
                        "error": "Google detected bot traffic and displayed a CAPTCHA.",
                        "engine": "google",
                        "results": [],
                    }
                return {
                    "status": "error",
                    "error": f"Search input element not found on page (Title: {title}).",
                    "engine": "google",
                    "results": [],
                }

            await search_box.fill(query)
            await search_box.press("Enter")

            # 3. Wait for search results
            try:
                await page.wait_for_selector(
                    "div#search, div.g, div[data-hveid], h3", timeout=12000
                )
                await page.wait_for_timeout(1500)
            except Exception:
                await page.wait_for_timeout(3000)

            # 4. Extract search results via page evaluation
            raw_results = await page.evaluate(
                """() => {
                const items = [];
                const h3s = document.querySelectorAll('h3');
                for (const h3 of h3s) {
                    const title = h3.innerText ? h3.innerText.trim() : '';
                    if (!title || title.includes('AI モード') || title.includes('AI による概要')) {
                        continue;
                    }
                    const a = h3.closest('a') || (h3.parentElement ? h3.parentElement.querySelector('a') : null);
                    if (!a) continue;

                    const container = h3.closest('div.g') || h3.closest('div[data-hveid]') || (a.parentElement ? a.parentElement.parentElement : null);
                    let citeText = '';
                    let snippetText = '';

                    if (container) {
                        const cite = container.querySelector('cite');
                        if (cite) citeText = cite.innerText.trim();

                        const snip = container.querySelector('div[style*="-webkit-line-clamp"], div.VwiC3b, span');
                        if (snip && snip.innerText && snip.innerText !== title) {
                            snippetText = snip.innerText.trim();
                        }
                    }

                    items.push({
                        title: title,
                        href: a.href || '',
                        cite: citeText,
                        snippet: snippetText
                    });
                }
                return items;
            }"""
            )

            # 5. Extract embedded full URLs from HTML to resolve /goto?url=
            html = await page.content()
            embedded_urls = re.findall(
                r'https?://[a-zA-Z0-9\.\-_/]+(?:/[a-zA-Z0-9\.\-_/]+)*', html
            )
            filtered_urls = [
                u
                for u in embedded_urls
                if not any(
                    x in u
                    for x in [
                        "google.com",
                        "google.co.jp",
                        "gstatic.com",
                        "schema.org",
                        "w3.org",
                        "youtube.com/s/",
                    ]
                )
            ]

            results = []
            seen_titles = set()

            for item in raw_results:
                title = item.get("title", "")
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                href = item.get("href", "")
                cite = item.get("cite", "")
                snippet = item.get("snippet", "")

                resolved_url = href
                if "/goto?url=" in href:
                    cite_cleaned = _clean_cite_url(cite)
                    matched_url = None
                    if cite_cleaned:
                        parts = cite_cleaned.split("/")
                        domain = parts[2] if len(parts) > 2 else ""
                        for u in filtered_urls:
                            if domain and domain in u:
                                matched_url = u
                                break
                    resolved_url = matched_url or cite_cleaned or href

                results.append(
                    {
                        "title": title,
                        "url": resolved_url,
                        "display_url": cite,
                        "snippet": snippet,
                    }
                )

                if len(results) >= max_results:
                    break

            return {
                "status": "success",
                "engine": "google",
                "query": query,
                "results": results,
            }
        finally:
            await browser.close()


async def search_duckduckgo_fast(
    query: str,
    max_results: int = 10,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Search DuckDuckGo via lightweight HTML endpoint (no browser, no API key)."""
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            },
        ) as client:
            resp = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
            )
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for r in soup.select("div.result"):
            # Skip advertisement elements
            if "result--ad" in r.get("class", []):
                continue

            a_url = r.select_one("a.result__url")
            h2_title = r.select_one("h2.result__title")
            a_snip = r.select_one("a.result__snippet")

            if not h2_title:
                continue

            title = h2_title.get_text(strip=True)
            raw_href = a_url["href"] if a_url and a_url.get("href") else ""
            if "duckduckgo.com/y.js" in raw_href or "ad_provider=" in raw_href:
                continue

            # DuckDuckGo wraps url in /l/?kh=-1&uddg=<encoded_url>
            match = re.search(r"uddg=([^&]+)", raw_href)
            actual_url = unquote(match.group(1)) if match else raw_href
            snippet = a_snip.get_text(strip=True) if a_snip else ""

            if actual_url:
                results.append(
                    {
                        "title": title,
                        "url": actual_url,
                        "display_url": actual_url,
                        "snippet": snippet,
                    }
                )

            if len(results) >= max_results:
                break

        return {
            "status": "success",
            "engine": "duckduckgo",
            "query": query,
            "results": results,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "engine": "duckduckgo",
            "results": [],
        }


async def search_web_unified(
    query: str,
    engine: Literal["google", "duckduckgo"] = "google",
    fallback_to_duckduckgo: bool = True,
    max_results: int = 10,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Unified search function supporting Google (via Playwright browser) and DuckDuckGo."""
    if engine == "google":
        res = await search_google_browser(
            query=query, max_results=max_results, timeout=timeout
        )
        if res.get("status") == "success" and len(res.get("results", [])) > 0:
            return res
        if fallback_to_duckduckgo:
            ddg_res = await search_duckduckgo_fast(
                query=query, max_results=max_results, timeout=timeout
            )
            ddg_res["fallback_from"] = "google"
            reason = res.get("error") or "No results returned by Google"
            ddg_res["note"] = f"Google search encountered issue ({reason}). Automatically fell back to DuckDuckGo."
            return ddg_res
        return res
    else:
        return await search_duckduckgo_fast(
            query=query, max_results=max_results, timeout=timeout
        )

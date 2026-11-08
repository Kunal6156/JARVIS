"""Quick web lookups without opening a browser."""
from ..registry import tool


@tool("Search the web and return the top results (title, link, snippet).",
      {"query": ("string", "Search query"), "max_results": ("integer", "Default 6")}, required=["query"])
def web_search(query, max_results=6):
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return "Web search needs: pip install ddgs"
    with DDGS() as d:
        results = list(d.text(query, max_results=int(max_results)))
    return "\n".join(f"{r.get('title')}\n{r.get('href')}\n{(r.get('body') or '')[:220]}\n" for r in results) or "No results."


@tool("Download a web page and return its readable text.",
      {"url": ("string", "Page URL"), "max_chars": ("integer", "Default 5000")}, required=["url"])
def fetch_url(url, max_chars=5000):
    import requests
    from bs4 import BeautifulSoup
    if not url.startswith("http"):
        url = "https://" + url
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (Jarvis)"})
    soup = BeautifulSoup(r.text, "html.parser")
    for t in soup(["script", "style", "nav", "footer", "noscript"]):
        t.decompose()
    return soup.get_text(" ", strip=True)[: int(max_chars)] or "(empty page)"

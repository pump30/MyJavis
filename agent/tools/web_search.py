"""Web search tool using Tavily."""

import httpx

TAVILY_API_KEY = "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"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"


async def web_search(query: str) -> str:
    """Search the web via Tavily and return top results as text."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(TAVILY_SEARCH_URL, json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": 5,
                "include_answer": True,
            })
            resp.raise_for_status()
            data = resp.json()

        parts = []
        # Tavily can return a direct answer
        answer = data.get("answer")
        if answer:
            parts.append(f"Summary: {answer}\n")

        results = data.get("results", [])
        if not results and not answer:
            return "No results found."

        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            content = r.get("content", "")
            url = r.get("url", "")
            parts.append(f"{i}. {title}\n   {content}\n   {url}")

        return "\n\n".join(parts)
    except Exception as e:
        return f"Search failed: {e}"

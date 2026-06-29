from backend.utils.logger import log_action


def web_search(query: str, max_results: int = 5) -> dict:
    clean = query.strip()

    if not clean:
        return {"ok": False, "error": "No search query provided."}

    try:
        try:
            from ddgs import DDGS
        except Exception:
            return {
                "ok": False,
                "query": clean,
                "error": "ddgs is not installed. Install project requirements to enable web_search.",
            }

        results = []

        with DDGS() as ddgs:
            for item in ddgs.text(clean, max_results=max_results):
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("href", ""),
                        "snippet": item.get("body", ""),
                    }
                )

        payload = {
            "ok": True,
            "query": clean,
            "results": results,
        }

        log_action("web_search", payload)
        return payload

    except Exception as e:
        payload = {
            "ok": False,
            "query": clean,
            "error": str(e),
        }
        log_action("web_search_error", payload)
        return payload

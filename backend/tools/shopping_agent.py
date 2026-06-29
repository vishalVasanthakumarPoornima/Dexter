from __future__ import annotations

import re
import time
import urllib.parse
from typing import Any

from backend.tools.browser_agent import _ensure_page, _goto, _page_state, _timeout_ms, _visible_text
from backend.utils.logger import log_action


def _ok(**payload: Any) -> dict[str, Any]:
    result = {"ok": True, "tool": "shopping_agent", **payload}
    log_action("shopping_agent", result)
    return result


def _fail(error: str, **payload: Any) -> dict[str, Any]:
    result = {"ok": False, "tool": "shopping_agent", "error": error, **payload}
    log_action("shopping_agent_error", result)
    return result


def _parse_price(value: str) -> float | None:
    match = re.search(r"\$?\s*([0-9]+(?:\.[0-9]{1,2})?)", value.replace(",", ""))
    if not match:
        return None
    return float(match.group(1))


def _parse_review_count(value: str) -> int:
    digits = re.sub(r"\D", "", value or "")
    return int(digits) if digits else 0


def _amazon_search_url(query: str, max_price: float | None) -> str:
    params = {"k": query}
    if max_price:
        # Amazon expects price filters in cents.
        params["rh"] = f"p_36:-{int(max_price * 100)}"
    return "https://www.amazon.com/s?" + urllib.parse.urlencode(params)


def _blocked_by_amazon(text: str) -> bool:
    lower = text.lower()
    return any(
        phrase in lower
        for phrase in (
            "enter the characters you see below",
            "sorry, we just need to make sure you're not a robot",
            "captcha",
        )
    )


def _extract_amazon_results(page) -> list[dict[str, Any]]:
    return page.evaluate(
        """
        () => Array.from(document.querySelectorAll('[data-component-type="s-search-result"]'))
          .map((card) => {
            const text = card.innerText || '';
            const titleEl = card.querySelector('h2 span')
              || card.querySelector('[data-cy="title-recipe"] span')
              || card.querySelector('a span');
            const linkEl = card.querySelector('h2 a')
              || card.querySelector('a.a-link-normal.s-no-outline');
            const priceEl = card.querySelector('.a-price .a-offscreen');
            const ratingEl = card.querySelector('.a-icon-alt');
            const reviewEl = Array.from(card.querySelectorAll('span.a-size-base, span.a-size-base.s-underline-text'))
              .find((el) => /^[0-9,]+$/.test((el.textContent || '').trim()));
            return {
              title: (titleEl?.textContent || '').trim(),
              url: linkEl?.href || '',
              priceText: (priceEl?.textContent || '').trim(),
              ratingText: (ratingEl?.textContent || '').trim(),
              reviewsText: (reviewEl?.textContent || '').trim(),
              sponsored: text.toLowerCase().includes('sponsored')
            };
          })
          .filter((item) => item.title && item.url)
        """
    )


def _normalize_result(item: dict[str, Any], max_price: float | None) -> dict[str, Any] | None:
    price = _parse_price(str(item.get("priceText") or ""))
    rating_match = re.search(r"([0-9](?:\.[0-9])?)\s+out of", str(item.get("ratingText") or ""))
    rating = float(rating_match.group(1)) if rating_match else 0.0
    reviews = _parse_review_count(str(item.get("reviewsText") or ""))

    if price is None:
        return None
    if max_price is not None and price > max_price:
        return None

    score = (rating * 1000) + min(reviews, 10000) / 10
    if item.get("sponsored"):
        score -= 250

    return {
        "title": str(item.get("title") or "").strip(),
        "url": str(item.get("url") or "").strip(),
        "price": price,
        "rating": rating,
        "reviews": reviews,
        "sponsored": bool(item.get("sponsored")),
        "score": score,
    }


def _current_product_price(page) -> float | None:
    text = page.evaluate(
        """
        () => {
          const selectors = [
            '#corePrice_feature_div .a-offscreen',
            '#priceblock_ourprice',
            '#priceblock_dealprice',
            '#apex_desktop .a-offscreen',
            '.a-price .a-offscreen'
          ];
          for (const selector of selectors) {
            const el = document.querySelector(selector);
            if (el?.textContent?.trim()) return el.textContent.trim();
          }
          return '';
        }
        """
    )
    return _parse_price(text or "")


def _add_to_cart_requirement(page) -> str:
    return page.evaluate(
        """
        () => {
          const button = document.querySelector('#add-to-cart-button');
          if (!button) return '';

          const style = window.getComputedStyle(button);
          const visible = !!(
            button.offsetWidth || button.offsetHeight || button.getClientRects().length
          ) && style.visibility !== 'hidden' && style.display !== 'none';
          const details = [
            button.getAttribute('data-hover'),
            button.getAttribute('aria-label'),
            button.getAttribute('title'),
            button.value,
            button.textContent,
          ].filter(Boolean).join(' ').replace(/<[^>]+>/g, ' ').replace(/\\s+/g, ' ').trim();
          const lower = details.toLowerCase();

          if (lower.includes('select') && (lower.includes('cart') || lower.includes('add'))) {
            return details;
          }
          if (button.disabled || button.getAttribute('aria-disabled') === 'true') {
            return details || 'Add to Cart is disabled until a product option is selected.';
          }
          if (!visible && lower.includes('select')) {
            return details;
          }
          return '';
        }
        """
    ).strip()


def shopping_agent(
    action: str = "research_add_to_cart",
    site: str = "amazon",
    query: str = "",
    max_price: float = 30,
    add_to_cart: bool = True,
    notes: str = "",
    timeout_seconds: float = 35,
) -> dict[str, Any]:
    clean_action = (action or "research_add_to_cart").strip().lower()
    clean_site = (site or "amazon").strip().lower()
    clean_query = (query or "").strip()

    if clean_site not in {"amazon", "amazon.com"}:
        return _fail("Only Amazon shopping is supported right now.", site=site)

    if clean_action not in {"research_add_to_cart", "research", "add_to_cart"}:
        return _fail(f"Unknown shopping action: {action}", action=action)

    if not clean_query:
        return _fail("query is required.", action=clean_action)

    max_price_value = float(max_price or 0)
    if max_price_value <= 0:
        max_price_value = 30.0

    candidates: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None

    try:
        page = _ensure_page(timeout_seconds=timeout_seconds)
        search_url = _amazon_search_url(clean_query, max_price_value)
        _goto(page, search_url, timeout_seconds)
        time.sleep(2)

        page_text = _visible_text(page, max_chars=6000)
        if _blocked_by_amazon(page_text):
            return _fail(
                "Amazon blocked the automated browser with a CAPTCHA or bot check.",
                action=clean_action,
                query=clean_query,
                search_url=search_url,
                **_page_state(page),
            )

        raw_results = _extract_amazon_results(page)
        candidates = [
            normalized
            for item in raw_results
            if (normalized := _normalize_result(item, max_price_value)) is not None
        ]
        candidates.sort(key=lambda item: item["score"], reverse=True)

        if not candidates:
            return _fail(
                f"No Amazon results under ${max_price_value:.2f} could be parsed.",
                action=clean_action,
                query=clean_query,
                search_url=search_url,
                **_page_state(page),
            )

        selected = candidates[0]

        if clean_action == "research" or not add_to_cart:
            return _ok(
                action=clean_action,
                query=clean_query,
                max_price=max_price_value,
                selected=selected,
                candidates=candidates[:5],
                output=(
                    f"Selected {selected['title']} at ${selected['price']:.2f} "
                    f"with {selected['rating']} stars and {selected['reviews']} reviews."
                ),
                **_page_state(page),
            )

        page.goto(selected["url"], wait_until="domcontentloaded", timeout=_timeout_ms(timeout_seconds))
        time.sleep(2)

        product_text = _visible_text(page, max_chars=8000)
        if _blocked_by_amazon(product_text):
            return _fail(
                "Amazon blocked the product page with a CAPTCHA or bot check.",
                action=clean_action,
                selected=selected,
                **_page_state(page),
            )

        product_price = _current_product_price(page)
        if product_price is not None and product_price > max_price_value:
            return _fail(
                f"Selected product price is now ${product_price:.2f}, above the ${max_price_value:.2f} limit.",
                action=clean_action,
                selected={**selected, "product_page_price": product_price},
                **_page_state(page),
            )

        add_to_cart_requirement = _add_to_cart_requirement(page)
        if add_to_cart_requirement:
            return _fail(
                "Amazon requires a product option before this item can be added to cart.",
                action=clean_action,
                query=clean_query,
                max_price=max_price_value,
                selected=selected,
                candidates=candidates[:5],
                variation_required=True,
                requirement=add_to_cart_requirement,
                output=(
                    "I found a candidate under budget, but Amazon requires a product option "
                    "before enabling Add to Cart. For reading glasses, tell me the strength "
                    "you want, such as +1.00, +1.50, or +2.00."
                ),
                **_page_state(page),
            )

        add_button = page.locator("#add-to-cart-button").first
        if add_button.count() == 0:
            add_button = page.get_by_text("Add to Cart", exact=False).first

        add_button.click(timeout=_timeout_ms(timeout_seconds))
        time.sleep(3)

        after_text = _visible_text(page, max_chars=8000)
        if "no thanks" in after_text.lower():
            try:
                page.get_by_text("No Thanks", exact=False).first.click(timeout=3000)
                time.sleep(1)
                after_text = _visible_text(page, max_chars=8000)
            except Exception:
                pass

        added = any(
            phrase in after_text.lower()
            for phrase in ("added to cart", "cart subtotal", "added to basket")
        )

        if not added:
            return _fail(
                "Clicked Add to Cart, but Amazon did not show a clear added-to-cart confirmation.",
                action=clean_action,
                selected=selected,
                **_page_state(page),
            )

        return _ok(
            action=clean_action,
            query=clean_query,
            max_price=max_price_value,
            selected=selected,
            candidates=candidates[:5],
            added_to_cart=True,
            checkout_clicked=False,
            output=(
                f"Added to cart: {selected['title']} at ${selected['price']:.2f}. "
                "I did not proceed to checkout."
            ),
            **_page_state(page),
        )
    except Exception as e:
        payload: dict[str, Any] = {"action": clean_action, "query": clean_query, "notes": notes}
        if selected:
            payload["selected"] = selected
        if candidates:
            payload["candidates"] = candidates[:5]
        return _fail(str(e), **payload)

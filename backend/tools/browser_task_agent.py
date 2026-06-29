from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
from typing import Any

from backend.models.ollama_client import chat_json_completion
from backend.tools.browser_agent import (
    _ensure_page,
    _goto,
    _page_state,
    _timeout_ms,
    _visible_text,
    reset_browser_agent_state,
    run_on_browser_thread,
)
from backend.utils.logger import log_action


DANGEROUS_BROWSER_PHRASES = (
    "buy now",
    "checkout",
    "check out",
    "place order",
    "submit order",
    "complete order",
    "confirm order",
    "payment",
    "pay now",
    "purchase",
)

KNOWN_SITE_URLS = {
    "hollister": "https://www.hollisterco.com/shop/us",
    "hollisterco": "https://www.hollisterco.com/shop/us",
    "abercrombie": "https://www.abercrombie.com/shop/us",
    "target": "https://www.target.com",
    "walmart": "https://www.walmart.com",
    "best buy": "https://www.bestbuy.com",
    "bestbuy": "https://www.bestbuy.com",
    "youtube": "https://www.youtube.com",
    "netflix": "https://www.netflix.com/search?q=",
    "whatsapp": "https://web.whatsapp.com",
    "whatsapp web": "https://web.whatsapp.com",
    "discord": "https://discord.com/channels/@me",
    "chatgpt": "https://chatgpt.com",
    "chat gpt": "https://chatgpt.com",
    "linkedin": "https://www.linkedin.com/jobs",
    "simplify": "https://simplify.jobs",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
}

LOGIN_HINTS = (
    "scan the qr code",
    "scan this qr code",
    "link a device",
    "use whatsapp on your computer",
    "sign in to continue",
    "log in to continue",
    "login to continue",
    "enter your password",
    "email or phone number",
    "email or mobile number",
    "welcome back",
    "log in with",
    "sign in with",
)

STALE_BROWSER_ERRORS = (
    "cannot switch to a different thread",
    "target page, context or browser has been closed",
    "browser has been closed",
    "target closed",
    "session closed",
)

BRIGHT_COLOR_TERMS = (
    "bright",
    "cream",
    "white",
    "yellow",
    "pink",
    "orange",
    "red",
    "neon",
)

DARK_COLOR_TERMS = (
    "black",
    "dark",
    "navy",
    "camo",
    "brown",
    "gray",
    "grey",
    "olive",
)

KNOWN_NETFLIX_TITLE_URLS = {
    "dhurandhar the revenge": "https://www.netflix.com/search?q=Dhurandhar+The+Revenge&jbv=82813021",
}


def _ok(**payload: Any) -> dict[str, Any]:
    result = {"ok": True, "tool": "browser_task_agent", **payload}
    log_action("browser_task_agent", result)
    return result


def _fail(error: str, **payload: Any) -> dict[str, Any]:
    result = {"ok": False, "tool": "browser_task_agent", "error": error, **payload}
    log_action("browser_task_agent_error", result)
    return result


def _infer_start_url(task: str, start_url: str = "") -> str:
    clean_url = (start_url or "").strip()
    if clean_url:
        return clean_url

    if match := re.search(r"https?://\S+", task):
        return match.group(0).rstrip(".,)")

    lower = task.lower()
    if "netflix" in lower:
        query = _infer_netflix_query(task)
        if query.lower() in KNOWN_NETFLIX_TITLE_URLS:
            return KNOWN_NETFLIX_TITLE_URLS[query.lower()]
        if query:
            return "https://www.netflix.com/search?q=" + urllib.parse.quote_plus(query)

    for name, url in KNOWN_SITE_URLS.items():
        if name in lower:
            return url

    if domain_match := re.search(r"\b([a-z0-9-]+\.(?:com|net|org|co|io|edu|gov))\b", lower):
        return "https://" + domain_match.group(1)

    return ""


def _infer_netflix_query(task: str) -> str:
    clean = re.split(r"\b(?:if|then|do not|don't|dont)\b", task, maxsplit=1, flags=re.I)[0]
    clean = re.sub(r"\bopen\s+netflix\s+and\s+", "", clean, flags=re.I)
    clean = re.sub(r"\b(?:on|in)\s+netflix\b", "", clean, flags=re.I)
    clean = re.sub(r"\bnetflix\b", "", clean, flags=re.I)
    clean = re.sub(r"\b(?:for\s+watching|and\s+start\s+playback|and\s+play\s+it|start\s+playback|playback)\b", "", clean, flags=re.I)

    if match := re.search(r"\b(?:open|play|start|watch|search(?:\s+for)?|find)\s+(.+)", clean, re.I):
        clean = match.group(1)

    clean = re.sub(r"\s+", " ", clean).strip(" .,!?:;\"'")
    return clean


def _extract_elements(page, limit: int = 80) -> list[dict[str, Any]]:
    return page.evaluate(
        """
        (limit) => {
          const visible = (el) => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.visibility !== 'hidden'
              && style.display !== 'none'
              && rect.width > 0
              && rect.height > 0;
          };
          const labelFor = (el) => {
            const text = [
              el.innerText,
              el.getAttribute('aria-label'),
              el.getAttribute('placeholder'),
              el.getAttribute('title'),
              el.getAttribute('name'),
              el.getAttribute('id'),
              el.value,
              el.href,
            ].filter(Boolean).join(' ');
            return text.replace(/\\s+/g, ' ').trim();
          };
          const nodes = Array.from(document.querySelectorAll(
            'a, button, input, textarea, select, option, [role="button"], [role="link"], [role="menuitem"], [tabindex]'
          ));
          const targets = [];
          for (const el of nodes) {
            if (!visible(el)) continue;
            const label = labelFor(el);
            if (!label && !['input', 'textarea', 'select'].includes(el.tagName.toLowerCase())) continue;
            targets.push(el);
            if (targets.length >= limit) break;
          }
          window.__dexterBrowserTargets = targets;
          return targets.map((el, index) => ({
            index,
            tag: el.tagName.toLowerCase(),
            role: el.getAttribute('role') || '',
            type: el.getAttribute('type') || '',
            text: labelFor(el).slice(0, 180),
            href: el.href || '',
            value: el.value || ''
          }));
        }
        """,
        limit,
    )


def _snapshot(page) -> dict[str, Any]:
    return {
        "title": page.title(),
        "url": page.url,
        "text": _visible_text(page, max_chars=5000),
        "elements": _extract_elements(page),
    }


def _login_required(state: dict[str, Any]) -> bool:
    text = str(state.get("text") or "").lower()
    url = str(state.get("url") or "").lower()
    title = str(state.get("title") or "").lower()
    combined = f"{title}\n{url}\n{text}"

    if "whatsapp" in url and any(phrase in combined for phrase in ("qr code", "link a device", "use whatsapp")):
        return True
    if "discord.com/login" in url or ("discord" in url and "welcome back" in combined and "password" in combined):
        return True
    if "netflix" in url and "who's watching" in combined:
        return True
    if "netflix" in url and "sign in" in combined and ("password" in combined or "email" in combined):
        return True
    if "chatgpt" in url and "log in" in combined and "sign up" in combined:
        return True

    return any(phrase in combined for phrase in LOGIN_HINTS)


def _wait_for_manual_login(page, initial_state: dict[str, Any], wait_seconds: float, history: list[str]) -> dict[str, Any] | None:
    if wait_seconds <= 0 or not _login_required(initial_state):
        return initial_state

    deadline = time.time() + wait_seconds
    history.append("Login required; waiting for manual login in the browser.")

    while time.time() < deadline:
        time.sleep(3)
        state = _snapshot(page)
        if not _login_required(state):
            history.append("Manual login appears complete; continuing.")
            return state

    return None


def _is_netflix_profile_gate(state: dict[str, Any]) -> bool:
    url = str(state.get("url") or "").lower()
    text = str(state.get("text") or "").lower()
    return "netflix" in url and "who's watching" in text


def _select_first_netflix_profile(page, state: dict[str, Any], history: list[str]) -> bool:
    if not _is_netflix_profile_gate(state):
        return False

    elements = list(state.get("elements") or [])
    for element in elements:
        index = int(element.get("index", -1))
        label = _element_label(elements, index).lower()
        if not label:
            continue
        if any(token in label for token in ("manage profiles", "add profile", "profile lock", "transfer profile")):
            continue
        if str(element.get("tag") or "").lower() not in {"a", "button", "div"} and element.get("role") != "button":
            continue
        if _run_index_action(page, index, "click"):
            history.append("Fast path: selected the first available Netflix profile.")
            time.sleep(1.5)
            return True

    return False


def _click_netflix_play(page, state: dict[str, Any], timeout_seconds: float, history: list[str]) -> bool:
    elements = list(state.get("elements") or [])
    play_index = _element_index_matching(elements, ("play",), ("trailer", "teaser", "preview", "games"))
    if play_index is not None:
        label = _element_label(elements, play_index)
        if _run_index_action(page, play_index, "click"):
            history.append(f"Fast path: clicked {label[:120] or 'Play'}.")
            time.sleep(1.5)
            return True

    candidates = [
        lambda: page.get_by_role("button", name=re.compile(r"^\s*play\s*$", re.I)).first,
        lambda: page.get_by_role("link", name=re.compile(r"^\s*play\s*$", re.I)).first,
        lambda: page.locator("[data-uia='play-button']").first,
        lambda: page.locator("button").filter(has_text=re.compile(r"^\s*Play\s*$", re.I)).first,
        lambda: page.locator("a").filter(has_text=re.compile(r"^\s*Play\s*$", re.I)).first,
    ]
    for make_locator in candidates:
        try:
            locator = make_locator()
            if locator.count() > 0 and locator.is_visible(timeout=750):
                locator.click(timeout=min(_timeout_ms(timeout_seconds), 5000))
                history.append("Fast path: clicked Netflix Play.")
                time.sleep(1.5)
                return True
        except Exception:
            continue

    return False


def _click_hollister_add_to_bag(page, timeout_seconds: float, history: list[str]) -> bool:
    patterns = [
        r"^\s*add\s+to\s+bag\s*$",
        r"^\s*add\s+to\s+cart\s*$",
        r"^\s*get\s+it\s+before\s+it'?s\s+gone\s*$",
    ]
    candidates = []
    for pattern in patterns:
        compiled = re.compile(pattern, re.I)
        candidates.extend(
            [
                lambda compiled=compiled: page.get_by_role("button", name=compiled).first,
                lambda compiled=compiled: page.locator("button").filter(has_text=compiled).first,
                lambda compiled=compiled: page.locator("[role='button']").filter(has_text=compiled).first,
            ]
        )

    for make_locator in candidates:
        try:
            locator = make_locator()
            if locator.count() > 0 and locator.is_visible(timeout=750):
                locator.scroll_into_view_if_needed(timeout=min(_timeout_ms(timeout_seconds), 5000))
                locator.click(timeout=min(_timeout_ms(timeout_seconds), 5000))
                history.append("Clicked Hollister Add to Bag.")
                time.sleep(2)
                return True
        except Exception:
            continue

    try:
        clicked_label = page.evaluate(
            """
            () => {
              const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.visibility !== 'hidden'
                  && style.display !== 'none'
                  && rect.width > 0
                  && rect.height > 0;
              };
              const labelFor = (el) => [
                el.innerText,
                el.getAttribute('aria-label'),
                el.getAttribute('title'),
                el.value,
              ].filter(Boolean).join(' ').replace(/\\s+/g, ' ').trim();
              const nodes = Array.from(document.querySelectorAll('button, [role="button"], input[type="button"], input[type="submit"]'));
              for (const el of nodes) {
                if (!visible(el) || el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                const label = labelFor(el);
                const lower = label.toLowerCase();
                if ((lower.includes('add to bag')
                    || lower.includes('add to cart')
                    || lower.includes("get it before it's gone")
                    || lower.includes('get it before its gone'))
                    && !lower.includes('checkout') && !lower.includes('payment')) {
                  el.scrollIntoView({ block: 'center', inline: 'center' });
                  el.click();
                  return label;
                }
              }
              return '';
            }
            """
        )
        if clicked_label:
            history.append(f"Clicked Hollister {clicked_label[:80]}.")
            time.sleep(2)
            return True
    except Exception:
        pass

    return False


def _run_netflix_fast_path(
    page,
    task: str,
    timeout_seconds: float,
    user_login_wait_seconds: float,
    history: list[str],
) -> dict[str, Any] | None:
    if "netflix" not in task.lower():
        return None

    query = _infer_netflix_query(task)
    if not query:
        return None

    known_url = KNOWN_NETFLIX_TITLE_URLS.get(query.lower())
    if known_url and not any(marker in page.url.lower() for marker in ("jbv=", "/watch/", "/title/")):
        _goto(page, known_url, timeout_seconds)
        history.append(f"Fast path: opened known Netflix title URL for {query}.")
        time.sleep(1.2)

    for step_number in range(1, 6):
        state = _snapshot(page)

        if _select_first_netflix_profile(page, state, history):
            continue

        if _login_required(state):
            state = _wait_for_manual_login(page, state, user_login_wait_seconds, history)
            if state is None:
                return _fail(
                    "Login is required before Dexter can continue this browser task.",
                    task=task,
                    login_required=True,
                    history=history,
                    output="I opened Netflix and waited for login, but login was not completed in time.",
                    **_page_state(page),
                )

        text = str(state.get("text") or "").lower()
        if "did not have any matches" in text:
            return _fail(
                f"Netflix did not find a match for {query}.",
                task=task,
                history=history,
                output=f"Netflix did not find a match for {query}.",
                **_page_state(page),
            )

        if _click_netflix_play(page, state, timeout_seconds, history):
            return _ok(
                task=task,
                steps_taken=step_number,
                history=history,
                output="Opened Netflix and started playback.",
                **_page_state(page),
            )

        raw_action = _fallback_action(task, state, history)
        if not raw_action:
            break

        action = str(raw_action.get("action") or "").strip().lower()
        if action == "done":
            return _ok(
                task=task,
                steps_taken=step_number,
                history=history,
                output=str(raw_action.get("summary") or "Opened Netflix."),
                **_page_state(page),
            )
        if action == "fail":
            reason = str(raw_action.get("reason") or "Netflix task cannot continue.").strip()
            return _fail(reason, task=task, history=history, output=reason, **_page_state(page))
        if action == "navigate":
            url = str(raw_action.get("url") or "").strip()
            if not url:
                break
            _goto(page, url, timeout_seconds)
            history.append(f"Fast path: navigated to {page.url}")
            time.sleep(1.2)
            continue
        if action == "click":
            index = int(raw_action.get("index"))
            label = _element_label(state.get("elements", []), index)
            if _run_index_action(page, index, "click"):
                history.append(f"Fast path: clicked {label[:120] or index}")
                if "play" in label.lower() and "trailer" not in label.lower():
                    time.sleep(1.5)
                    return _ok(
                        task=task,
                        steps_taken=step_number,
                        history=history,
                        output="Opened Netflix and started playback.",
                        **_page_state(page),
                    )
                time.sleep(1.2)
                continue
            break

    history.append("Fast path: no deterministic Netflix action completed; falling back to browser controller.")
    return None


def _dangerous_text(value: str) -> bool:
    lower = (value or "").lower()
    return any(phrase in lower for phrase in DANGEROUS_BROWSER_PHRASES)


def _infer_max_price(task: str) -> float | None:
    match = re.search(
        r"\b(?:under|below|less than|max(?:imum)?|up to)\s+\$?\s*(\d+(?:\.\d{1,2})?)",
        task,
        re.I,
    )
    return float(match.group(1)) if match else None


def _requested_size(task: str) -> str:
    match = re.search(r"\b(?:size\s+is|size|in)\s+(xxl|xl|xs|s|m|l)\b", task, re.I)
    return match.group(1).upper() if match else ""


def _element_index_matching(
    elements: list[dict[str, Any]],
    includes: tuple[str, ...],
    excludes: tuple[str, ...] = (),
) -> int | None:
    for element in elements:
        label = _element_label(elements, int(element.get("index", -1))).lower()
        if all(term.lower() in label for term in includes) and not any(term.lower() in label for term in excludes):
            return int(element.get("index"))
    return None


def _prices_from_label(label: str) -> list[float]:
    return [float(match) for match in re.findall(r"\$(\d+(?:\.\d{1,2})?)", label)]


def _hollister_product_score(label: str, max_price: float | None, avoid_bright: bool) -> float | None:
    lower = label.lower()
    if "hoodie" not in lower or "clearance" not in lower:
        return None
    if any(term in lower for term in ("sweatpants", "joggers", "shorts")):
        return None

    prices = _prices_from_label(label)
    sale_price = min(prices) if prices else 999.0
    if max_price is not None and sale_price > max_price:
        return None

    score = 1000.0 - sale_price
    if any(term in lower for term in DARK_COLOR_TERMS):
        score += 80
    if "faded black" in lower or "washed dark" in lower:
        score += 40
    if avoid_bright and any(term in lower for term in BRIGHT_COLOR_TERMS):
        score -= 160
    if "leopard" in lower:
        score -= 120
    return score


def _best_hollister_product_index(task: str, elements: list[dict[str, Any]]) -> int | None:
    max_price = _infer_max_price(task)
    avoid_bright = any(phrase in task.lower() for phrase in ("not too bright", "not bright", "darker", "dark"))
    best_index: int | None = None
    best_score: float | None = None

    for element in elements:
        if element.get("tag") != "a":
            continue
        index = int(element.get("index", -1))
        label = _element_label(elements, index)
        score = _hollister_product_score(label, max_price, avoid_bright)
        if score is None:
            continue
        if best_score is None or score > best_score:
            best_score = score
            best_index = index

    return best_index


def _fallback_action(task: str, state: dict[str, Any], history: list[str] | None = None) -> dict[str, Any] | None:
    lower_task = task.lower()
    url = str(state.get("url") or "").lower()
    text = str(state.get("text") or "").lower()
    elements = list(state.get("elements") or [])
    history_text = "\n".join(history or []).lower()

    if "stop after it opens" in lower_task and state.get("url"):
        return {"action": "done", "summary": f"Successfully navigated to {state.get('url')} and the page has loaded."}

    if "hollister" in lower_task and "hoodie" in lower_task:
        if (
            (("clearance" in lower_task or "sale" in lower_task) and "/shop/us/p/" not in url)
            and "mens-sweatshirts-and-sweatpants-clearance" not in url
        ):
            return {
                "action": "navigate",
                "url": "https://www.hollisterco.com/shop/us/mens-sweatshirts-and-sweatpants-clearance?pagefm=navigation",
                "reason": "Open men's clearance sweatshirts directly.",
            }

        if "/shop/us/p/" in url:
            if "add to bag" in history_text or "add selected hoodie to bag" in history_text:
                return {"action": "done", "summary": "Selected a Hollister clearance hoodie and added it to the bag."}

            size = _requested_size(task)
            if size:
                size_already_clicked = any(
                    token in history_text
                    for token in (
                        f"size {size.lower()}",
                        f"_{size.lower()}",
                        f" {size.lower()}_p",
                        f" {size.lower()} ",
                    )
                )
                if size_already_clicked:
                    size = ""

            if size:
                size_index = _element_index_matching(
                    elements,
                    (size.lower(),),
                    ("size guide", "unavailable", "out of stock", "sold out"),
                )
                if size_index is not None:
                    return {"action": "click", "index": size_index, "reason": f"Select requested size {size}."}

            if "add" in lower_task and ("cart" in lower_task or "bag" in lower_task):
                add_index = _element_index_matching(elements, ("add", "bag"), ("checkout", "payment", "purchase"))
                if add_index is None:
                    add_index = _element_index_matching(elements, ("add", "cart"), ("checkout", "payment", "purchase"))
                if add_index is None:
                    add_index = _element_index_matching(elements, ("get it before", "gone"), ("checkout", "payment", "purchase"))
                if add_index is not None:
                    return {"action": "click", "index": add_index, "reason": "Add selected hoodie to bag."}
                return {"action": "wait", "seconds": 1, "reason": "Wait for the Hollister add-to-bag control."}

            if "added" in text or "item was added" in text:
                return {"action": "done", "summary": "Selected a Hollister clearance hoodie and added it to the bag."}

        if "mens-sweatshirts-and-sweatpants-clearance" in url:
            product_index = _best_hollister_product_index(task, elements)
            if product_index is not None:
                return {"action": "click", "index": product_index, "reason": "Open best matching clearance hoodie."}

        if "mens-clearance" in url:
            nav_index = _element_index_matching(elements, ("sweatshirts", "sweatpants"))
            if nav_index is not None:
                return {"action": "click", "index": nav_index, "reason": "Open men's clearance sweatshirts."}

        if "sale" in url:
            mens_index = _element_index_matching(elements, ("shop men's",))
            if mens_index is not None:
                return {"action": "click", "index": mens_index, "reason": "Open men's sale section."}

        sale_index = _element_index_matching(elements, ("cat-label-177705",))
        if sale_index is None:
            sale_index = _element_index_matching(elements, ("https://www.hollisterco.com/shop/us/sale",))
        if sale_index is not None:
            return {"action": "click", "index": sale_index, "reason": "Open sale section."}

    if "add" in lower_task and "cart" in lower_task:
        add_index = _element_index_matching(elements, ("add", "cart"), ("checkout", "payment", "purchase"))
        if add_index is None:
            add_index = _element_index_matching(elements, ("add", "bag"), ("checkout", "payment", "purchase"))
        if add_index is not None:
            return {"action": "click", "index": add_index, "reason": "Add item to cart or bag."}

    if "netflix" in lower_task:
        query = _infer_netflix_query(task).lower()
        if "clicked play" in history_text or "start netflix playback" in history_text:
            return {"action": "done", "summary": "Opened Netflix and started playback."}
        if "did not have any matches" in text:
            return {"action": "fail", "reason": f"Netflix did not find a match for {query or 'the requested title'}."}
        if query in KNOWN_NETFLIX_TITLE_URLS and not any(marker in url for marker in ("jbv=", "/watch/", "/title/")):
            return {
                "action": "navigate",
                "url": KNOWN_NETFLIX_TITLE_URLS[query],
                "reason": "Open known Netflix title page directly.",
            }
        if query and "jbv=" not in url:
            title_index = None
            for element in elements:
                if str(element.get("tag") or "").lower() in {"input", "textarea", "select"}:
                    continue
                label = _element_label(elements, int(element.get("index", -1))).lower()
                if all(term in label for term in query.split()[:2]):
                    title_index = int(element.get("index", -1))
                    break
            if title_index is not None:
                return {"action": "click", "index": title_index, "reason": "Open matching Netflix title."}
        if any(marker in url for marker in ("jbv=", "/title/", "/watch/")) or (
            query and query in (str(state.get("title") or "") + "\n" + text).lower()
        ):
            play_index = _element_index_matching(elements, ("play",), ("trailer", "teaser", "preview", "games"))
            if play_index is not None:
                return {"action": "click", "index": play_index, "reason": "Start Netflix playback."}

    return None


def _element_label(elements: list[dict[str, Any]], index: int) -> str:
    for element in elements:
        if element.get("index") == index:
            return " ".join(
                str(element.get(key, ""))
                for key in ("text", "href", "role", "type")
                if element.get(key)
            )
    return ""


def _run_index_action(page, index: int, action: str, value: str = "") -> bool:
    return bool(
        page.evaluate(
            """
            ({ index, action, value }) => {
              const el = window.__dexterBrowserTargets?.[index];
              if (!el) return false;
              el.scrollIntoView({ block: 'center', inline: 'center' });
              if (action === 'click') {
                el.click();
                return true;
              }
              if (action === 'fill') {
                el.focus();
                if ('value' in el) el.value = value;
                else el.textContent = value;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
              }
              if (action === 'select') {
                if (el.tagName.toLowerCase() !== 'select') return false;
                const wanted = value.toLowerCase();
                const option = Array.from(el.options).find((candidate) => {
                  return candidate.value.toLowerCase() === wanted
                    || candidate.textContent.trim().toLowerCase() === wanted
                    || candidate.textContent.trim().toLowerCase().includes(wanted);
                });
                if (!option) return false;
                el.value = option.value;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
              }
              return false;
            }
            """,
            {"index": index, "action": action, "value": value},
        )
    )


def _build_action_prompt(task: str, state: dict[str, Any], history: list[str]) -> list[dict[str, str]]:
    compact_state = {
        "title": state.get("title", ""),
        "url": state.get("url", ""),
        "visible_text": str(state.get("text", ""))[:3500],
        "elements": state.get("elements", [])[:80],
    }

    system_prompt = """
You are Dexter's browser task controller.

Choose exactly one next browser action and return only valid JSON.

Supported JSON actions:
{"action":"navigate","url":"https://example.com"}
{"action":"click","index":0}
{"action":"fill","index":0,"text":"value"}
{"action":"select","index":0,"value":"XL"}
{"action":"press","key":"Enter"}
{"action":"scroll","direction":"down","amount":5}
{"action":"wait","seconds":2}
{"action":"done","summary":"what was completed"}
{"action":"fail","reason":"why it cannot continue"}

Rules:
- Use only the listed element indexes for click, fill, and select.
- For clothing size requests, select the requested exact size before adding to cart.
- For price-limited shopping, do not choose an item over the requested budget.
- You may add an item to cart if the user asked for it.
- Never click checkout, buy now, place order, submit order, payment, purchase, or final confirmation.
- If checkout or payment is required, stop with fail.
- If a required user choice is missing, stop with fail and ask for that choice.
- If the page requires login, wait for the user to log in manually before continuing.
"""

    user_prompt = (
        f"Task:\n{task}\n\n"
        f"History:\n" + "\n".join(history[-8:]) + "\n\n"
        f"Current browser state:\n{json.dumps(compact_state, ensure_ascii=True)}"
    )

    return [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_prompt},
    ]


def browser_task_agent(
    task: str,
    start_url: str = "",
    max_steps: int = 18,
    timeout_seconds: float = 35,
    user_login_wait_seconds: float | None = None,
    allow_purchase: bool = False,
    _retry_after_stale: bool = False,
) -> dict[str, Any]:
    clean_task = (task or "").strip()
    if not clean_task:
        return _fail("task is required.")

    if allow_purchase:
        return _fail("Purchases and checkout are not allowed through Dexter browser automation.")

    if _dangerous_text(clean_task) and "cart" not in clean_task.lower():
        return _fail("This browser task appears to involve checkout or purchasing, which is not allowed.")

    if user_login_wait_seconds is None:
        user_login_wait_seconds = float(os.getenv("DEXTER_BROWSER_LOGIN_WAIT_SECONDS", "180"))
    total_timeout_seconds = float(os.getenv("DEXTER_BROWSER_TASK_TOTAL_TIMEOUT_SECONDS", "180"))
    deadline = time.time() + total_timeout_seconds

    history: list[str] = []

    try:
        page = _ensure_page(timeout_seconds=timeout_seconds)
        destination = _infer_start_url(clean_task, start_url=start_url)
        if destination:
            _goto(page, destination, timeout_seconds)
            time.sleep(2)
            history.append(f"Opened {page.url}")

        fast_result = _run_netflix_fast_path(
            page,
            clean_task,
            float(timeout_seconds),
            float(user_login_wait_seconds),
            history,
        )
        if fast_result is not None:
            return fast_result

        for step_number in range(1, max(1, int(max_steps)) + 1):
            if time.time() > deadline:
                return _fail(
                    f"Stopped after {int(total_timeout_seconds)} seconds without completing the browser task.",
                    task=clean_task,
                    history=history,
                    output="The browser task took too long and was stopped.",
                    **_page_state(page),
                )

            state = _snapshot(page)
            state = _wait_for_manual_login(page, state, float(user_login_wait_seconds), history)
            if state is None:
                return _fail(
                    "Login is required before Dexter can continue this browser task.",
                    task=clean_task,
                    login_required=True,
                    history=history,
                    output="I opened the page and waited for login, but login was not completed in time.",
                    **_page_state(page),
                )

            raw_action = _fallback_action(clean_task, state, history)
            if raw_action:
                history.append(f"Step {step_number}: deterministic browser fallback selected {raw_action.get('action')}")
            else:
                try:
                    raw_action = chat_json_completion(
                        messages=_build_action_prompt(clean_task, state, history),
                        timeout=int(os.getenv("DEXTER_BROWSER_ACTION_MODEL_TIMEOUT", "15")),
                        options={"temperature": 0, "num_ctx": 4096, "num_predict": 800},
                    )
                except Exception as e:
                    fallback = _fallback_action(clean_task, state, history)
                    if not fallback:
                        raise
                    raw_action = fallback
                    history.append(f"Step {step_number}: used deterministic fallback after model action error: {str(e)[:120]}")

            action = str(raw_action.get("action") or "").strip().lower()

            if action == "done":
                summary = str(raw_action.get("summary") or "Browser task completed.").strip()
                return _ok(
                    task=clean_task,
                    steps_taken=step_number - 1,
                    history=history,
                    output=summary,
                    **_page_state(page),
                )

            if action == "fail":
                reason = str(raw_action.get("reason") or "Browser task cannot continue.").strip()
                return _fail(
                    reason,
                    task=clean_task,
                    steps_taken=step_number - 1,
                    history=history,
                    output=reason,
                    **_page_state(page),
                )

            if action == "navigate":
                url = str(raw_action.get("url") or "").strip()
                if not url:
                    return _fail("Browser task chose navigate without a URL.", task=clean_task, history=history)
                _goto(page, url, timeout_seconds)
                time.sleep(2)
                history.append(f"Step {step_number}: navigated to {page.url}")
                continue

            if action == "click":
                index = int(raw_action.get("index"))
                label = _element_label(state.get("elements", []), index)
                if _dangerous_text(label):
                    return _fail(
                        f"Stopped before clicking a protected checkout/payment control: {label[:120]}",
                        task=clean_task,
                        history=history,
                        **_page_state(page),
                    )
                if not _run_index_action(page, index, "click"):
                    return _fail(f"Could not click browser element index {index}.", task=clean_task, history=history)
                time.sleep(2)
                history.append(f"Step {step_number}: clicked {label[:120] or index}")
                lower_label = label.lower()
                if "hollister" in clean_task.lower() and any(marker in page.url.lower() for marker in ("/shop/us/p/", "/p/")):
                    if "add" in lower_label and ("bag" in lower_label or "cart" in lower_label):
                        return _ok(
                            task=clean_task,
                            steps_taken=step_number,
                            history=history,
                            output="Selected a Hollister clearance hoodie and added it to the bag.",
                            **_page_state(page),
                        )
                    requested_size = _requested_size(clean_task)
                    requested_size_clicked = requested_size and re.search(
                        rf"(^|[^a-z0-9]){re.escape(requested_size.lower())}([^a-z0-9]|$)",
                        lower_label,
                    )
                    if requested_size_clicked and ("add" in clean_task.lower()) and (
                        "cart" in clean_task.lower() or "bag" in clean_task.lower()
                    ):
                        if _click_hollister_add_to_bag(page, float(timeout_seconds), history):
                            return _ok(
                                task=clean_task,
                                steps_taken=step_number,
                                history=history,
                                output=f"Selected a Hollister clearance hoodie in size {requested_size} and added it to the bag.",
                                **_page_state(page),
                            )
                continue

            if action in {"fill", "select"}:
                index = int(raw_action.get("index"))
                value = str(raw_action.get("text") or raw_action.get("value") or "").strip()
                if not value:
                    return _fail(f"Browser task chose {action} without a value.", task=clean_task, history=history)
                if _dangerous_text(value):
                    return _fail("Stopped before entering protected checkout/payment text.", task=clean_task, history=history)
                if not _run_index_action(page, index, action, value):
                    return _fail(f"Could not {action} browser element index {index}.", task=clean_task, history=history)
                time.sleep(1)
                history.append(f"Step {step_number}: {action} element {index} with {value}")
                continue

            if action == "press":
                key = str(raw_action.get("key") or "Enter").strip()
                page.keyboard.press(key)
                time.sleep(1.5)
                history.append(f"Step {step_number}: pressed {key}")
                continue

            if action == "scroll":
                direction = str(raw_action.get("direction") or "down").strip().lower()
                amount = int(raw_action.get("amount") or 5)
                signed_amount = -abs(amount) if direction == "up" else abs(amount)
                page.mouse.wheel(0, signed_amount * 240)
                time.sleep(1)
                history.append(f"Step {step_number}: scrolled {direction}")
                continue

            if action == "wait":
                seconds = float(raw_action.get("seconds") or 2)
                time.sleep(max(0.5, min(seconds, 8)))
                history.append(f"Step {step_number}: waited")
                continue

            return _fail(f"Browser task chose unsupported action: {action}", task=clean_task, history=history)

        return _fail(
            f"Stopped after {max_steps} browser steps without completing the task.",
            task=clean_task,
            history=history,
            output="I could not complete the browser task within the step limit.",
            **_page_state(page),
        )
    except Exception as e:
        error_text = str(e)
        if not _retry_after_stale and any(token in error_text.lower() for token in STALE_BROWSER_ERRORS):
            reset_browser_agent_state()
            return browser_task_agent(
                task=clean_task,
                start_url=start_url,
                max_steps=max_steps,
                timeout_seconds=timeout_seconds,
                user_login_wait_seconds=user_login_wait_seconds,
                allow_purchase=False,
                _retry_after_stale=True,
            )
        return _fail(str(e), task=clean_task, history=history)


_browser_task_agent_impl = browser_task_agent


def browser_task_agent(
    task: str,
    start_url: str = "",
    max_steps: int = 18,
    timeout_seconds: float = 35,
    user_login_wait_seconds: float | None = None,
    allow_purchase: bool = False,
    _retry_after_stale: bool = False,
) -> dict[str, Any]:
    return run_on_browser_thread(
        _browser_task_agent_impl,
        task=task,
        start_url=start_url,
        max_steps=max_steps,
        timeout_seconds=timeout_seconds,
        user_login_wait_seconds=user_login_wait_seconds,
        allow_purchase=allow_purchase,
        _retry_after_stale=_retry_after_stale,
    )

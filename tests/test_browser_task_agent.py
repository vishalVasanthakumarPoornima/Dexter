import unittest

from backend.tools.browser_task_agent import _fallback_action, _infer_start_url, _login_required


class BrowserTaskFallbackTests(unittest.TestCase):
    def test_netflix_known_title_starts_at_direct_title_url(self):
        url = _infer_start_url("Open Netflix and watch Dhurandhar The Revenge")

        self.assertEqual(
            url,
            "https://www.netflix.com/search?q=Dhurandhar+The+Revenge&jbv=82813021",
        )

    def test_netflix_profile_picker_requires_manual_step(self):
        state = {
            "url": "https://www.netflix.com/browse",
            "title": "Netflix",
            "text": "Who's watching?",
        }

        self.assertTrue(_login_required(state))

    def test_hollister_home_navigates_directly_to_clearance_category(self):
        state = {
            "url": "https://www.hollisterco.com/shop/us",
            "text": "",
            "elements": [
                {
                    "index": 1,
                    "tag": "button",
                    "text": "Summer Sale! Up to 40% Off Select Styles",
                },
                {
                    "index": 15,
                    "tag": "a",
                    "text": "Sale cat-label-177705",
                    "href": "https://www.hollisterco.com/shop/us/sale",
                },
            ],
        }

        action = _fallback_action("hollister clearance hoodie size XL add it to cart", state)

        self.assertEqual(
            action,
            {
                "action": "navigate",
                "url": "https://www.hollisterco.com/shop/us/mens-sweatshirts-and-sweatpants-clearance?pagefm=navigation",
                "reason": "Open men's clearance sweatshirts directly.",
            },
        )

    def test_hollister_listing_selects_dark_under_budget_hoodie(self):
        state = {
            "url": "https://www.hollisterco.com/shop/us/mens-sweatshirts-and-sweatpants-clearance",
            "text": "",
            "elements": [
                {
                    "index": 10,
                    "tag": "a",
                    "text": "Bright Cream Hoodie Was $59.95, now $19.99 Clearance",
                    "href": "/cream-hoodie",
                },
                {
                    "index": 11,
                    "tag": "a",
                    "text": "Hollister Feel Good Boxy Dodge Demon Graphic Zip-Up Hoodie Faded Black Was $59.95, now $24.99 Clearance",
                    "href": "/faded-black-hoodie",
                },
            ],
        }

        action = _fallback_action(
            "Open hollister, find a hoodie on clearance for men in size XL, "
            "and if the color is not too bright, then add it to cart and tell me. "
            "Do not checkout or purchase.",
            state,
        )

        self.assertEqual(action, {"action": "click", "index": 11, "reason": "Open best matching clearance hoodie."})

    def test_hollister_product_selects_requested_size_before_add_to_bag(self):
        state = {
            "url": "https://www.hollisterco.com/shop/us/p/faded-black-hoodie",
            "text": "Hollister Feel Good Hoodie",
            "elements": [
                {"index": 1, "tag": "button", "text": "M"},
                {"index": 2, "tag": "button", "text": "XL"},
                {"index": 3, "tag": "button", "text": "Add to Bag"},
            ],
        }

        action = _fallback_action("hollister hoodie size XL add it to cart", state)

        self.assertEqual(action, {"action": "click", "index": 2, "reason": "Select requested size XL."})

    def test_hollister_product_waits_for_add_button_instead_of_sale_nav(self):
        state = {
            "url": "https://www.hollisterco.com/shop/us/p/faded-black-hoodie",
            "text": "Hollister Feel Good Hoodie",
            "elements": [
                {
                    "index": 15,
                    "tag": "a",
                    "text": "Sale cat-label-177705",
                    "href": "https://www.hollisterco.com/shop/us/sale",
                },
            ],
        }

        action = _fallback_action(
            "Open hollister, search for a mens hoodie on clearance in size XL, and add it to cart",
            state,
            history=["Step 3: clicked pdp_size-primary pdp_radio_size_primary_XL XL_p radio"],
        )

        self.assertEqual(
            action,
            {"action": "wait", "seconds": 1, "reason": "Wait for the Hollister add-to-bag control."},
        )

    def test_hollister_product_get_it_before_gone_is_add_to_bag(self):
        state = {
            "url": "https://www.hollisterco.com/shop/us/p/faded-black-hoodie",
            "text": "Hollister Feel Good Hoodie",
            "elements": [
                {"index": 3, "tag": "button", "text": "Get It Before It's Gone"},
            ],
        }

        action = _fallback_action(
            "Open hollister, search for a mens hoodie on clearance in size XL, and add it to cart",
            state,
            history=["Step 3: clicked pdp_size-primary pdp_radio_size_primary_XL XL_p radio"],
        )

        self.assertEqual(action, {"action": "click", "index": 3, "reason": "Add selected hoodie to bag."})

    def test_netflix_title_page_clicks_play(self):
        state = {
            "url": "https://www.netflix.com/search?q=Dhurandhar%20The%20Revenge&jbv=82813021",
            "title": "Dhurandhar The Revenge (Raw & Undekha) - Netflix",
            "text": "Play 2026 3h 52m Dhurandhar The Revenge",
            "elements": [
                {"index": 4, "tag": "button", "text": "Play"},
                {"index": 5, "tag": "button", "text": "Play Trailer"},
            ],
        }

        action = _fallback_action("Open Netflix and watch Dhurandhar The Revenge", state)

        self.assertEqual(action, {"action": "click", "index": 4, "reason": "Start Netflix playback."})

    def test_netflix_title_path_clicks_play(self):
        state = {
            "url": "https://www.netflix.com/title/82813021",
            "title": "Home - Netflix",
            "text": "Play 2026 3h 52m Hamza continues his fight against Karachi",
            "elements": [
                {"index": 4, "tag": "button", "text": "Play"},
            ],
        }

        action = _fallback_action("Open Netflix and watch Dhurandhar The Revenge", state)

        self.assertEqual(action, {"action": "click", "index": 4, "reason": "Start Netflix playback."})

    def test_netflix_known_title_navigates_to_title_page_from_search(self):
        state = {
            "url": "https://www.netflix.com/search?q=Dhurandhar+The+Revenge",
            "title": "Netflix",
            "text": "Search",
            "elements": [
                {"index": 1, "tag": "input", "text": "Titles, people, genres Dhurandhar The Revenge"},
            ],
        }

        action = _fallback_action("Open Netflix and watch Dhurandhar The Revenge", state)

        self.assertEqual(
            action,
            {
                "action": "navigate",
                "url": "https://www.netflix.com/search?q=Dhurandhar+The+Revenge&jbv=82813021",
                "reason": "Open known Netflix title page directly.",
            },
        )


if __name__ == "__main__":
    unittest.main()

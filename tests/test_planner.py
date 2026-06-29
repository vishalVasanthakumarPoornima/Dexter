import os
import unittest

from backend.agents.planner import determine_plan, normalize_plan


class PlannerHeuristicTests(unittest.TestCase):
    def setUp(self):
        os.environ["DEXTER_DISABLE_LLM_PLANNER"] = "1"

    def test_open_brave_and_lookup_is_multi_step(self):
        plan = determine_plan("open brave and look up latest AI news")

        self.assertTrue(plan["requires_tools"])
        self.assertEqual(
            [step["tool"] for step in plan["steps"]],
            ["open_app", "brave_search"],
        )
        self.assertEqual(plan["steps"][0]["args"], {"app": "Brave Browser"})
        self.assertEqual(plan["steps"][1]["args"], {"query": "latest AI news"})

    def test_close_spotify(self):
        plan = determine_plan("close spotify")

        self.assertEqual(plan["action"], "close_app")
        self.assertEqual(plan["steps"][0]["args"], {"app": "Spotify"})

    def test_youtube_search_opens_brave_search(self):
        plan = determine_plan("search youtube for Matt Wolfe videos")

        self.assertEqual(plan["action"], "brave_search")
        self.assertEqual(
            plan["steps"][0]["args"],
            {"query": "site:youtube.com Matt Wolfe videos"},
        )

    def test_summary_request_uses_web_search_context(self):
        plan = determine_plan("summarize Matt Wolfe latest video and write a LinkedIn post")

        self.assertEqual(plan["action"], "web_search")
        self.assertEqual(
            [step["tool"] for step in plan["steps"]],
            ["web_search", "file_controller"],
        )
        self.assertEqual(
            plan["steps"][0]["args"],
            {"query": "summarize Matt Wolfe latest video and write a LinkedIn post"},
        )

    def test_apply_latest_swe_jobs_uses_job_agent(self):
        plan = determine_plan("apply for the latest SWE jobs")

        self.assertEqual(plan["action"], "job_application_agent")
        self.assertEqual([step["tool"] for step in plan["steps"]], ["job_application_agent"])
        self.assertEqual(plan["steps"][0]["args"]["action"], "start")
        self.assertEqual(plan["steps"][0]["args"]["query"], "apply for the latest SWE jobs")
        self.assertTrue(plan["steps"][0]["args"]["auto_apply"])

    def test_apply_latest_swe_internships_uses_job_agent(self):
        plan = determine_plan("apply for the latest SWE internships")

        self.assertEqual(plan["action"], "job_application_agent")
        self.assertEqual(plan["steps"][0]["args"]["query"], "apply for the latest SWE internships")
        self.assertTrue(plan["steps"][0]["args"]["auto_apply"])

    def test_amazon_shopping_cart_request_uses_shopping_agent(self):
        plan = determine_plan(
            "Open amazon.com, browse for the best reading glasses under $30 "
            "by comparing reviews and brands, add one good option to my cart, "
            "but do not purchase or checkout."
        )

        self.assertEqual(plan["action"], "shopping_agent")
        args = plan["steps"][0]["args"]
        self.assertEqual(args["action"], "research_add_to_cart")
        self.assertEqual(args["site"], "amazon")
        self.assertEqual(args["query"], "reading glasses")
        self.assertEqual(args["max_price"], 30.0)
        self.assertTrue(args["add_to_cart"])

    def test_hollister_cart_request_uses_browser_task_agent(self):
        plan = determine_plan(
            "Find the hoodies on clearance and choose one and add to my cart "
            "in hollister and make sure that the hoodie is under $30, my size is XL."
        )

        self.assertEqual(plan["action"], "browser_task_agent")
        args = plan["steps"][0]["args"]
        self.assertIn("hollister", args["task"].lower())
        self.assertEqual(args["start_url"], "https://www.hollisterco.com/shop/us")
        self.assertFalse(args["allow_purchase"])

    def test_browser_navigate_alias_normalizes_to_browser_agent(self):
        plan = normalize_plan(
            {
                "tool": "browser_navigate",
                "url": "https://www.hollisterco.com",
                "reason": "Navigate to Hollister website.",
            },
            source="test",
            message="open hollister",
        )

        self.assertEqual(plan["action"], "browser_agent")
        self.assertEqual(plan["steps"][0]["args"]["action"], "open_url")
        self.assertEqual(plan["steps"][0]["args"]["url"], "https://www.hollisterco.com")

    def test_go_to_browser_sentence_does_not_treat_sentence_as_url(self):
        plan = determine_plan("go to hollister.com in the browser and stop after it opens")

        self.assertEqual(plan["action"], "browser_task_agent")
        self.assertEqual(plan["steps"][0]["args"]["start_url"], "https://www.hollisterco.com/shop/us")

    def test_netflix_title_task_uses_browser_task_agent(self):
        plan = determine_plan("open Dhurandhar 1 on netflix for watching and start it")

        self.assertEqual(plan["action"], "browser_task_agent")
        self.assertIn("netflix.com/search", plan["steps"][0]["args"]["start_url"])
        self.assertFalse(plan["steps"][0]["args"]["allow_purchase"])

    def test_netflix_title_task_does_not_include_login_instructions_in_query(self):
        plan = determine_plan(
            "Open Netflix and watch Dhurandhar The Revenge. If profile selection or login is required, "
            "wait for me to choose a profile or log in, then continue and start playback."
        )

        self.assertEqual(plan["action"], "browser_task_agent")
        self.assertEqual(
            plan["steps"][0]["args"]["start_url"],
            "https://www.netflix.com/search?q=Dhurandhar+The+Revenge",
        )

    def test_open_whatsapp_send_text_routes_to_send_message(self):
        plan = determine_plan("open whatsapp and send a text to my dad saying test message")

        self.assertEqual(plan["action"], "send_message")
        args = plan["steps"][0]["args"]
        self.assertEqual(args["platform"], "whatsapp")
        self.assertEqual(args["receiver"], "my dad")
        self.assertEqual(args["message_text"], "test message")

    def test_send_resume_to_dad_whatsapp_routes_to_resume_share(self):
        plan = determine_plan("find my resume locally and send it to dad through whatsapp")

        self.assertEqual(plan["action"], "send_resume_whatsapp")
        args = plan["steps"][0]["args"]
        self.assertEqual(args["receiver"], "dad")
        self.assertEqual(args["query"], "resume")
        self.assertEqual(args["root"], "home")
        self.assertTrue(args["auto_send"])

    def test_send_resume_to_dad_whatsapp_draft_only(self):
        plan = determine_plan("send my resume to my dad through whatsapp draft only")

        self.assertEqual(plan["action"], "send_resume_whatsapp")
        args = plan["steps"][0]["args"]
        self.assertEqual(args["receiver"], "my dad")
        self.assertFalse(args["auto_send"])

    def test_whatsapp_resume_alias_normalizes(self):
        plan = normalize_plan(
            {"tool": "whatsapp_resume", "recipient": "dad", "query": "resume", "dry_run": True},
            source="test",
            message="send my resume to dad through whatsapp",
        )

        self.assertEqual(plan["action"], "send_resume_whatsapp")
        args = plan["steps"][0]["args"]
        self.assertEqual(args["receiver"], "dad")
        self.assertEqual(args["query"], "resume")
        self.assertTrue(args["dry_run"])

    def test_whatsapp_body_with_job_words_still_routes_to_send_message(self):
        plan = determine_plan(
            "open whatsapp and send a text to dad saying Dexter helps me find jobs, "
            "open websites, and tailor resumes"
        )

        self.assertEqual(plan["action"], "send_message")
        args = plan["steps"][0]["args"]
        self.assertEqual(args["platform"], "whatsapp")
        self.assertEqual(args["receiver"], "dad")
        self.assertEqual(args["message_text"], "Dexter helps me find jobs, open websites, and tailor resumes")

    def test_whatsapp_message_dry_run_does_not_send(self):
        plan = determine_plan("send a whatsapp message to my dad saying test message dry run only")

        self.assertEqual(plan["action"], "send_message")
        args = plan["steps"][0]["args"]
        self.assertEqual(args["receiver"], "my dad")
        self.assertEqual(args["message_text"], "test message")
        self.assertFalse(args["auto_send"])
        self.assertTrue(args["dry_run"])

    def test_whatsapp_message_draft_only_does_not_auto_send(self):
        plan = determine_plan("send a whatsapp message to Alex saying running late draft only")

        self.assertEqual(plan["action"], "send_message")
        args = plan["steps"][0]["args"]
        self.assertEqual(args["message_text"], "running late")
        self.assertFalse(args["auto_send"])
        self.assertNotIn("dry_run", args)

    def test_discord_message_routes_to_browser_task_agent(self):
        plan = determine_plan("open discord and send a message to Alex saying test message")

        self.assertEqual(plan["action"], "browser_task_agent")
        self.assertIn("discord.com", plan["steps"][0]["args"]["start_url"])

    def test_all_portals_signup_uses_job_agent_not_chat(self):
        plan = determine_plan(
            "use all portals and sign me up using my gmail account "
            "candidate@example.com and save password to Brave"
        )

        self.assertEqual(plan["action"], "job_application_agent")
        args = plan["steps"][0]["args"]
        self.assertEqual(args["action"], "signup")
        self.assertEqual(args["email"], "candidate@example.com")
        self.assertEqual(args["source_scope"], "all")
        self.assertTrue(args["save_password_to_brave"])
        self.assertTrue(args["check_pages"])
        self.assertTrue(args["brave_group"])

    def test_morning_internship_automation_uses_job_automation_agent(self):
        plan = determine_plan(
            "Automate checking for new 2027 posted internships for CS students every morning at 8am"
        )

        self.assertEqual(plan["action"], "job_automation_agent")
        args = plan["steps"][0]["args"]
        self.assertEqual(args["action"], "setup")
        self.assertEqual(args["automation_id"], "morning_2027_cs_internships")
        self.assertEqual(args["time"], "8am")
        self.assertEqual(args["source_scope"], "all")
        self.assertTrue(args["install_launch_agent"])

    def test_job_automation_status_does_not_create_schedule(self):
        plan = determine_plan("job automation status")

        self.assertEqual(plan["action"], "job_automation_agent")
        self.assertEqual(plan["steps"][0]["args"]["action"], "status")

    def test_run_job_automation_does_not_create_schedule(self):
        plan = determine_plan("run job automation")

        self.assertEqual(plan["action"], "job_automation_agent")
        self.assertEqual(plan["steps"][0]["args"]["action"], "run")
        self.assertEqual(plan["steps"][0]["args"]["automation_id"], "morning_2027_cs_internships")

    def test_disable_job_automation_does_not_create_schedule(self):
        plan = determine_plan("disable job automation")

        self.assertEqual(plan["action"], "job_automation_agent")
        self.assertEqual(plan["steps"][0]["args"]["action"], "disable")
        self.assertEqual(plan["steps"][0]["args"]["automation_id"], "morning_2027_cs_internships")

    def test_finder_search_json_alias_searches_home(self):
        plan = normalize_plan(
            {"tool": "finder_search", "query": "The Deal", "scope": "all"},
            source="test",
            message="Find the book The Deal in finder and open it",
        )

        self.assertEqual(plan["action"], "search_files")
        self.assertEqual(plan["steps"][0]["args"]["query"], "The Deal")
        self.assertEqual(plan["steps"][0]["args"]["root"], "home")

    def test_whatsapp_message_uses_send_message_tool(self):
        plan = determine_plan("send a whatsapp message to Alex saying running late")

        self.assertEqual(plan["action"], "send_message")
        args = plan["steps"][0]["args"]
        self.assertEqual(args["receiver"], "Alex")
        self.assertEqual(args["message_text"], "running late")
        self.assertEqual(args["platform"], "whatsapp")
        self.assertTrue(args["auto_send"])

    def test_search_all_my_files_uses_home_root(self):
        plan = determine_plan("search all my files for resume")

        self.assertEqual(plan["action"], "search_files")
        self.assertEqual(plan["steps"][0]["args"]["query"], "resume")
        self.assertEqual(plan["steps"][0]["args"]["root"], "home")

    def test_tool_audit_request_uses_audit_tool(self):
        plan = determine_plan("check if all tools work")

        self.assertEqual(plan["action"], "audit_tools")
        self.assertFalse(plan["steps"][0]["args"]["include_side_effects"])

    def test_browser_status_uses_browser_agent(self):
        plan = determine_plan("dexter browser status")

        self.assertEqual(plan["action"], "browser_agent")
        self.assertEqual(plan["steps"][0]["args"], {"action": "status"})

    def test_existing_browser_session_attach_uses_browser_agent(self):
        plan = determine_plan("use the already opened tab")

        self.assertEqual(plan["action"], "browser_agent")
        self.assertEqual(plan["steps"][0]["args"], {"action": "attach_existing_session"})

    def test_existing_browser_session_relaunch_still_requires_explicit_wording(self):
        plan = determine_plan("relaunch existing browser session")

        self.assertEqual(plan["action"], "browser_agent")
        self.assertEqual(plan["steps"][0]["args"], {"action": "relaunch_existing_session"})

    def test_controlled_browser_open_url_uses_browser_agent(self):
        plan = determine_plan("open https://example.com in the controlled browser")

        self.assertEqual(plan["action"], "browser_agent")
        self.assertEqual(plan["steps"][0]["args"]["action"], "open_url")
        self.assertEqual(plan["steps"][0]["args"]["url"], "https://example.com")


if __name__ == "__main__":
    unittest.main()

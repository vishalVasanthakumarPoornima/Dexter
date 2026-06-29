import asyncio
import os
import threading
import unittest
from tempfile import TemporaryDirectory

from backend.tools.assistant_tools import _lookup_contact_phone, send_message
from backend.tools.browser_agent import browser_agent, run_on_browser_thread
from backend.tools.resume_share import send_resume_whatsapp
from backend.tools.tool_audit import audit_tools


class ToolBehaviorTests(unittest.TestCase):
    def test_send_message_dry_run_does_not_claim_sent(self):
        result = send_message(
            receiver="Alex",
            message_text="running late",
            platform="whatsapp",
            dry_run=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["platform"], "whatsapp")
        self.assertEqual(result["status"], "dry_run")
        self.assertFalse(result["sent"])

    def test_send_message_whatsapp_uses_browser_contact_name(self):
        import backend.tools.browser_agent as browser_agent

        calls = []
        original = browser_agent.send_whatsapp_via_brave

        def fake_send_whatsapp_via_brave(
            phone="",
            message_text="",
            receiver="",
            auto_send=True,
            timeout_seconds=45,
        ):
            calls.append(
                {
                    "phone": phone,
                    "message_text": message_text,
                    "receiver": receiver,
                    "auto_send": auto_send,
                }
            )
            return {
                "ok": True,
                "tool": "browser_agent",
                "platform": "whatsapp",
                "status": "drafted",
                "sent": False,
                "output": "Drafted WhatsApp message.",
            }

        browser_agent.send_whatsapp_via_brave = fake_send_whatsapp_via_brave
        try:
            result = send_message(
                receiver="my dad",
                message_text="test",
                platform="whatsapp",
                auto_send=False,
            )
        finally:
            browser_agent.send_whatsapp_via_brave = original

        self.assertTrue(result["ok"])
        self.assertEqual(calls[0]["phone"], "")
        self.assertEqual(calls[0]["receiver"], "my dad")
        self.assertEqual(calls[0]["message_text"], "test")

    def test_contact_alias_resolves_my_prefix_without_macos_contacts(self):
        with TemporaryDirectory() as temp_dir:
            old_path = os.environ.get("DEXTER_CONTACT_ALIASES_PATH")
            old_roots = os.environ.get("DEXTER_SAFE_FILE_ROOTS")
            alias_path = os.path.join(temp_dir, "contacts.json")
            os.environ["DEXTER_CONTACT_ALIASES_PATH"] = alias_path
            os.environ["DEXTER_SAFE_FILE_ROOTS"] = temp_dir
            with open(alias_path, "w", encoding="utf-8") as file:
                file.write('{"dad": "+1 (555) 123-4567"}')

            try:
                phone, error = _lookup_contact_phone("my dad")
            finally:
                if old_path is None:
                    os.environ.pop("DEXTER_CONTACT_ALIASES_PATH", None)
                else:
                    os.environ["DEXTER_CONTACT_ALIASES_PATH"] = old_path
                if old_roots is None:
                    os.environ.pop("DEXTER_SAFE_FILE_ROOTS", None)
                else:
                    os.environ["DEXTER_SAFE_FILE_ROOTS"] = old_roots

        self.assertEqual(phone, "+15551234567")
        self.assertEqual(error, "")

    def test_tool_audit_runs_safe_smoke_tests(self):
        result = audit_tools()

        self.assertIn("results", result)
        self.assertGreaterEqual(result["total"], result["passed"])
        self.assertEqual(result["failed"], 0)

    def test_browser_agent_status_is_safe(self):
        result = browser_agent(action="status")

        self.assertTrue(result["ok"])
        self.assertIn("profile_dir", result)
        self.assertIn("runtime_ready", result)

    def test_browser_thread_wrapper_runs_outside_asyncio_loop_thread(self):
        async def call_from_event_loop():
            event_loop_thread = threading.get_ident()
            browser_thread = run_on_browser_thread(threading.get_ident)
            return event_loop_thread, browser_thread

        event_loop_thread, browser_thread = asyncio.run(call_from_event_loop())

        self.assertNotEqual(event_loop_thread, browser_thread)

    def test_browser_thread_wrapper_ignores_stale_worker_thread_id(self):
        import backend.tools.browser_agent as browser_agent

        original_worker_id = browser_agent._BROWSER_WORKER_THREAD_ID
        original_impl = browser_agent._send_whatsapp_file_via_brave_impl

        def fake_file_send(**_kwargs):
            return {
                "ok": True,
                "tool": "browser_agent",
                "thread_id": threading.get_ident(),
            }

        async def call_from_event_loop():
            event_loop_thread = threading.get_ident()
            browser_agent._BROWSER_WORKER_THREAD_ID = event_loop_thread
            browser_agent._send_whatsapp_file_via_brave_impl = fake_file_send
            result = browser_agent.send_whatsapp_file_via_brave(
                receiver="my dad",
                file_path="backend/main.py",
                auto_send=False,
            )
            return event_loop_thread, result

        try:
            event_loop_thread, result = asyncio.run(call_from_event_loop())
        finally:
            browser_agent._BROWSER_WORKER_THREAD_ID = original_worker_id
            browser_agent._send_whatsapp_file_via_brave_impl = original_impl

        self.assertTrue(result["ok"])
        self.assertNotEqual(event_loop_thread, result["thread_id"])

    def test_cdp_auto_launch_uses_remote_debugging_port(self):
        import backend.tools.browser_agent as browser_agent

        old_auto = os.environ.get("DEXTER_BROWSER_AUTO_LAUNCH_CDP")
        old_app = os.environ.get("DEXTER_BROWSER_APP_NAME")
        original_popen = browser_agent.subprocess.Popen
        original_reachable = browser_agent._browser_cdp_reachable
        commands = []

        class FakeProcess:
            pass

        def fake_popen(command, **_kwargs):
            commands.append(command)
            return FakeProcess()

        def fake_reachable(_url):
            return bool(commands)

        os.environ["DEXTER_BROWSER_AUTO_LAUNCH_CDP"] = "true"
        os.environ["DEXTER_BROWSER_APP_NAME"] = "Brave Browser"
        browser_agent.subprocess.Popen = fake_popen
        browser_agent._browser_cdp_reachable = fake_reachable
        try:
            browser_agent._auto_launch_cdp_browser("http://127.0.0.1:9222", timeout_seconds=3)
        finally:
            browser_agent.subprocess.Popen = original_popen
            browser_agent._browser_cdp_reachable = original_reachable
            if old_auto is None:
                os.environ.pop("DEXTER_BROWSER_AUTO_LAUNCH_CDP", None)
            else:
                os.environ["DEXTER_BROWSER_AUTO_LAUNCH_CDP"] = old_auto
            if old_app is None:
                os.environ.pop("DEXTER_BROWSER_APP_NAME", None)
            else:
                os.environ["DEXTER_BROWSER_APP_NAME"] = old_app

        self.assertEqual(commands[0][:3], ["open", "-a", "Brave Browser"])
        self.assertNotIn("-n", commands[0])
        self.assertIn("--remote-debugging-port=9222", commands[0])
        self.assertIn("--restore-last-session", commands[0])

    def test_cdp_relaunch_existing_session_reopens_default_profile(self):
        import backend.tools.browser_agent as browser_agent

        old_app = os.environ.get("DEXTER_BROWSER_APP_NAME")
        old_force = os.environ.get("DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING")
        original_browser_executable = browser_agent._browser_executable
        original_run = browser_agent.subprocess.run
        original_popen = browser_agent.subprocess.Popen
        original_reachable = browser_agent._browser_cdp_reachable
        commands = []

        class FakeProcess:
            pass

        def fake_run(command, **_kwargs):
            commands.append(("run", command))
            if command[:2] == ["pgrep", "-x"]:
                return browser_agent.subprocess.CompletedProcess(command, 1, "", "")
            return browser_agent.subprocess.CompletedProcess(command, 0, "", "")

        def fake_popen(command, **_kwargs):
            commands.append(("popen", command))
            return FakeProcess()

        def fake_reachable(_url):
            return any(kind == "popen" for kind, _command in commands)

        os.environ["DEXTER_BROWSER_APP_NAME"] = "Brave Browser"
        os.environ["DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING"] = "false"
        browser_agent._browser_executable = lambda: "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
        browser_agent.subprocess.run = fake_run
        browser_agent.subprocess.Popen = fake_popen
        browser_agent._browser_cdp_reachable = fake_reachable
        try:
            relaunched = browser_agent._relaunch_existing_cdp_browser("http://127.0.0.1:9222", timeout_seconds=3)
        finally:
            browser_agent._browser_executable = original_browser_executable
            browser_agent.subprocess.run = original_run
            browser_agent.subprocess.Popen = original_popen
            browser_agent._browser_cdp_reachable = original_reachable
            if old_app is None:
                os.environ.pop("DEXTER_BROWSER_APP_NAME", None)
            else:
                os.environ["DEXTER_BROWSER_APP_NAME"] = old_app
            if old_force is None:
                os.environ.pop("DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING", None)
            else:
                os.environ["DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING"] = old_force

        self.assertTrue(relaunched)
        popen_commands = [command for kind, command in commands if kind == "popen"]
        self.assertEqual(popen_commands[0][0], "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")
        self.assertNotIn("open", popen_commands[0])
        self.assertNotIn("--user-data-dir", " ".join(popen_commands[0]))
        self.assertIn("--remote-debugging-port=9222", popen_commands[0])
        self.assertIn("--restore-last-session", popen_commands[0])

    def test_cdp_relaunch_can_force_quit_when_graceful_quit_fails(self):
        import backend.tools.browser_agent as browser_agent

        old_app = os.environ.get("DEXTER_BROWSER_APP_NAME")
        old_force = os.environ.get("DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING")
        original_browser_executable = browser_agent._browser_executable
        original_run = browser_agent.subprocess.run
        original_popen = browser_agent.subprocess.Popen
        original_reachable = browser_agent._browser_cdp_reachable
        commands = []
        state = {"force_quit": False}

        class FakeProcess:
            pass

        def fake_run(command, **_kwargs):
            commands.append(("run", command))
            if command[:2] == ["pgrep", "-x"]:
                return browser_agent.subprocess.CompletedProcess(command, 1 if state["force_quit"] else 0, "", "")
            if command[:2] == ["pkill", "-x"]:
                state["force_quit"] = True
            return browser_agent.subprocess.CompletedProcess(command, 0, "", "")

        def fake_popen(command, **_kwargs):
            commands.append(("popen", command))
            return FakeProcess()

        def fake_reachable(_url):
            return any(kind == "popen" for kind, _command in commands)

        os.environ["DEXTER_BROWSER_APP_NAME"] = "Brave Browser"
        os.environ["DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING"] = "true"
        browser_agent._browser_executable = lambda: "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
        browser_agent.subprocess.run = fake_run
        browser_agent.subprocess.Popen = fake_popen
        browser_agent._browser_cdp_reachable = fake_reachable
        try:
            relaunched = browser_agent._relaunch_existing_cdp_browser("http://127.0.0.1:9222", timeout_seconds=3)
        finally:
            browser_agent._browser_executable = original_browser_executable
            browser_agent.subprocess.run = original_run
            browser_agent.subprocess.Popen = original_popen
            browser_agent._browser_cdp_reachable = original_reachable
            if old_app is None:
                os.environ.pop("DEXTER_BROWSER_APP_NAME", None)
            else:
                os.environ["DEXTER_BROWSER_APP_NAME"] = old_app
            if old_force is None:
                os.environ.pop("DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING", None)
            else:
                os.environ["DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING"] = old_force

        self.assertTrue(relaunched)
        self.assertIn(("run", ["pkill", "-x", "Brave Browser"]), commands)
        self.assertIn(
            ("run", ["pkill", "-f", "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]),
            commands,
        )

    def test_cdp_status_is_ready_when_fallback_profile_enabled(self):
        import backend.tools.browser_agent as browser_agent

        old_connection = os.environ.get("DEXTER_BROWSER_CONNECTION")
        old_auto = os.environ.get("DEXTER_BROWSER_AUTO_LAUNCH_CDP")
        old_relaunch = os.environ.get("DEXTER_BROWSER_CDP_RELAUNCH_EXISTING")
        old_force = os.environ.get("DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING")
        old_fallback = os.environ.get("DEXTER_BROWSER_CDP_FALLBACK_PERSISTENT")
        original_browser_executable = browser_agent._browser_executable
        original_cdp_reachable = browser_agent._browser_cdp_reachable

        os.environ["DEXTER_BROWSER_CONNECTION"] = "cdp"
        os.environ["DEXTER_BROWSER_AUTO_LAUNCH_CDP"] = "false"
        os.environ["DEXTER_BROWSER_CDP_RELAUNCH_EXISTING"] = "false"
        os.environ["DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING"] = "false"
        os.environ["DEXTER_BROWSER_CDP_FALLBACK_PERSISTENT"] = "true"
        browser_agent._browser_executable = lambda: "/tmp/fake-browser"
        browser_agent._browser_cdp_reachable = lambda _url: False
        try:
            status = browser_agent._runtime_ready()
        finally:
            browser_agent._browser_executable = original_browser_executable
            browser_agent._browser_cdp_reachable = original_cdp_reachable
            for key, old_value in (
                ("DEXTER_BROWSER_CONNECTION", old_connection),
                ("DEXTER_BROWSER_AUTO_LAUNCH_CDP", old_auto),
                ("DEXTER_BROWSER_CDP_RELAUNCH_EXISTING", old_relaunch),
                ("DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING", old_force),
                ("DEXTER_BROWSER_CDP_FALLBACK_PERSISTENT", old_fallback),
            ):
                if old_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old_value

        self.assertFalse(status["cdp_reachable"])
        self.assertTrue(status["cdp_fallback_persistent_enabled"])
        self.assertTrue(status["runtime_ready"])

    def test_cdp_status_is_not_ready_when_attach_only_session_missing(self):
        import backend.tools.browser_agent as browser_agent

        old_connection = os.environ.get("DEXTER_BROWSER_CONNECTION")
        old_auto = os.environ.get("DEXTER_BROWSER_AUTO_LAUNCH_CDP")
        old_relaunch = os.environ.get("DEXTER_BROWSER_CDP_RELAUNCH_EXISTING")
        old_force = os.environ.get("DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING")
        old_fallback = os.environ.get("DEXTER_BROWSER_CDP_FALLBACK_PERSISTENT")
        original_browser_executable = browser_agent._browser_executable
        original_cdp_reachable = browser_agent._browser_cdp_reachable

        os.environ["DEXTER_BROWSER_CONNECTION"] = "cdp"
        os.environ["DEXTER_BROWSER_AUTO_LAUNCH_CDP"] = "false"
        os.environ["DEXTER_BROWSER_CDP_RELAUNCH_EXISTING"] = "false"
        os.environ["DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING"] = "false"
        os.environ["DEXTER_BROWSER_CDP_FALLBACK_PERSISTENT"] = "false"
        browser_agent._browser_executable = lambda: "/tmp/fake-browser"
        browser_agent._browser_cdp_reachable = lambda _url: False
        try:
            status = browser_agent._runtime_ready()
        finally:
            browser_agent._browser_executable = original_browser_executable
            browser_agent._browser_cdp_reachable = original_cdp_reachable
            for key, old_value in (
                ("DEXTER_BROWSER_CONNECTION", old_connection),
                ("DEXTER_BROWSER_AUTO_LAUNCH_CDP", old_auto),
                ("DEXTER_BROWSER_CDP_RELAUNCH_EXISTING", old_relaunch),
                ("DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING", old_force),
                ("DEXTER_BROWSER_CDP_FALLBACK_PERSISTENT", old_fallback),
            ):
                if old_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old_value

        self.assertFalse(status["cdp_reachable"])
        self.assertFalse(status["cdp_auto_launch_enabled"])
        self.assertFalse(status["cdp_fallback_persistent_enabled"])
        self.assertFalse(status["runtime_ready"])

    def test_cdp_status_relaunch_enabled_does_not_make_attach_ready(self):
        import backend.tools.browser_agent as browser_agent

        old_connection = os.environ.get("DEXTER_BROWSER_CONNECTION")
        old_auto = os.environ.get("DEXTER_BROWSER_AUTO_LAUNCH_CDP")
        old_relaunch = os.environ.get("DEXTER_BROWSER_CDP_RELAUNCH_EXISTING")
        old_force = os.environ.get("DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING")
        old_fallback = os.environ.get("DEXTER_BROWSER_CDP_FALLBACK_PERSISTENT")
        original_browser_executable = browser_agent._browser_executable
        original_cdp_reachable = browser_agent._browser_cdp_reachable

        os.environ["DEXTER_BROWSER_CONNECTION"] = "cdp"
        os.environ["DEXTER_BROWSER_AUTO_LAUNCH_CDP"] = "false"
        os.environ["DEXTER_BROWSER_CDP_RELAUNCH_EXISTING"] = "true"
        os.environ["DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING"] = "true"
        os.environ["DEXTER_BROWSER_CDP_FALLBACK_PERSISTENT"] = "false"
        browser_agent._browser_executable = lambda: "/tmp/fake-browser"
        browser_agent._browser_cdp_reachable = lambda _url: False
        try:
            status = browser_agent._runtime_ready()
        finally:
            browser_agent._browser_executable = original_browser_executable
            browser_agent._browser_cdp_reachable = original_cdp_reachable
            for key, old_value in (
                ("DEXTER_BROWSER_CONNECTION", old_connection),
                ("DEXTER_BROWSER_AUTO_LAUNCH_CDP", old_auto),
                ("DEXTER_BROWSER_CDP_RELAUNCH_EXISTING", old_relaunch),
                ("DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING", old_force),
                ("DEXTER_BROWSER_CDP_FALLBACK_PERSISTENT", old_fallback),
            ):
                if old_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old_value

        self.assertTrue(status["cdp_relaunch_existing_enabled"])
        self.assertTrue(status["cdp_force_quit_existing_enabled"])
        self.assertFalse(status["cdp_reachable"])
        self.assertFalse(status["runtime_ready"])

    def test_browser_agent_can_relaunch_existing_session(self):
        import backend.tools.browser_agent as browser_agent

        old_connection = os.environ.get("DEXTER_BROWSER_CONNECTION")
        old_url = os.environ.get("DEXTER_BROWSER_CDP_URL")
        original_relaunch = browser_agent._relaunch_existing_cdp_browser
        original_runtime_ready = browser_agent._runtime_ready
        calls = []

        os.environ["DEXTER_BROWSER_CONNECTION"] = "cdp"
        os.environ["DEXTER_BROWSER_CDP_URL"] = "http://127.0.0.1:9222"
        browser_agent._relaunch_existing_cdp_browser = lambda url, timeout_seconds=20: calls.append((url, timeout_seconds)) or True
        browser_agent._runtime_ready = lambda: {
            "browser_connection": "cdp",
            "cdp_url": "http://127.0.0.1:9222",
            "cdp_reachable": True,
            "runtime_ready": True,
        }
        try:
            result = browser_agent._browser_agent_impl(action="relaunch_existing_session", timeout_seconds=3)
        finally:
            browser_agent._relaunch_existing_cdp_browser = original_relaunch
            browser_agent._runtime_ready = original_runtime_ready
            if old_connection is None:
                os.environ.pop("DEXTER_BROWSER_CONNECTION", None)
            else:
                os.environ["DEXTER_BROWSER_CONNECTION"] = old_connection
            if old_url is None:
                os.environ.pop("DEXTER_BROWSER_CDP_URL", None)
            else:
                os.environ["DEXTER_BROWSER_CDP_URL"] = old_url

        self.assertTrue(result["ok"])
        self.assertTrue(result["runtime_ready"])
        self.assertEqual(calls, [("http://127.0.0.1:9222", 3)])

    def test_browser_agent_attach_existing_session_does_not_relaunch(self):
        import backend.tools.browser_agent as browser_agent

        old_connection = os.environ.get("DEXTER_BROWSER_CONNECTION")
        old_url = os.environ.get("DEXTER_BROWSER_CDP_URL")
        original_relaunch = browser_agent._relaunch_existing_cdp_browser
        original_reachable = browser_agent._browser_cdp_reachable
        original_runtime_ready = browser_agent._runtime_ready
        calls = []

        os.environ["DEXTER_BROWSER_CONNECTION"] = "cdp"
        os.environ["DEXTER_BROWSER_CDP_URL"] = "http://127.0.0.1:9222"
        browser_agent._relaunch_existing_cdp_browser = lambda url, timeout_seconds=20: calls.append((url, timeout_seconds)) or True
        browser_agent._browser_cdp_reachable = lambda _url: False
        browser_agent._runtime_ready = lambda: {
            "browser_connection": "cdp",
            "cdp_url": "http://127.0.0.1:9222",
            "cdp_reachable": False,
            "runtime_ready": False,
        }
        try:
            result = browser_agent._browser_agent_impl(action="attach_existing_session", timeout_seconds=3)
        finally:
            browser_agent._relaunch_existing_cdp_browser = original_relaunch
            browser_agent._browser_cdp_reachable = original_reachable
            browser_agent._runtime_ready = original_runtime_ready
            if old_connection is None:
                os.environ.pop("DEXTER_BROWSER_CONNECTION", None)
            else:
                os.environ["DEXTER_BROWSER_CONNECTION"] = old_connection
            if old_url is None:
                os.environ.pop("DEXTER_BROWSER_CDP_URL", None)
            else:
                os.environ["DEXTER_BROWSER_CDP_URL"] = old_url

        self.assertFalse(result["ok"])
        self.assertEqual(calls, [])
        self.assertIn("did not quit or relaunch Brave", result["error"])

    def test_whatsapp_login_detector_matches_current_qr_copy(self):
        import backend.tools.browser_agent as browser_agent

        login_text = (
            "Download WhatsApp for Mac\n"
            "Scan to log in\n"
            "Scan the QR code with your phone's camera\n"
            "Link with phone number instead."
        )

        self.assertTrue(browser_agent._whatsapp_login_required(login_text))

    def test_whatsapp_selectors_cover_visible_chat_list_and_current_search_label(self):
        import backend.tools.browser_agent as browser_agent

        self.assertIn("div[role='listitem']", browser_agent.WHATSAPP_CHAT_ROW_SELECTORS)
        self.assertIn(
            "div[contenteditable='true'][aria-label='Search or start new chat']",
            browser_agent.WHATSAPP_SEARCH_SELECTORS,
        )
        self.assertIn(
            "button[aria-label='Search or start new chat']",
            browser_agent.WHATSAPP_SEARCH_BUTTON_SELECTORS,
        )
        self.assertIn(
            "button[role='menuitem'][aria-label='Document']",
            browser_agent.WHATSAPP_DOCUMENT_SELECTORS,
        )
        self.assertNotIn(
            "div[contenteditable='true'][role='textbox']",
            browser_agent.WHATSAPP_CAPTION_SELECTORS,
        )

    def test_whatsapp_document_upload_rejects_media_only_inputs(self):
        import backend.tools.browser_agent as browser_agent

        self.assertFalse(browser_agent._whatsapp_accepts_document_upload("image/*"))
        self.assertFalse(browser_agent._whatsapp_accepts_document_upload("image/*,video/*"))
        self.assertTrue(browser_agent._whatsapp_accepts_document_upload(""))
        self.assertTrue(browser_agent._whatsapp_accepts_document_upload(".pdf,application/pdf"))

    def test_whatsapp_file_attachment_rejection_is_detected(self):
        import backend.tools.browser_agent as browser_agent

        self.assertTrue(
            browser_agent._whatsapp_file_attachment_rejected(
                "1 file you tried adding is not supported."
            )
        )

    def test_job_automation_setup_status_without_launch_agent(self):
        with TemporaryDirectory() as temp_dir:
            os.environ["DEXTER_JOB_AUTOMATION_DIR"] = os.path.join(temp_dir, "automations")
            os.environ["DEXTER_JOB_AUTOMATION_RUNS_DIR"] = os.path.join(temp_dir, "runs")

            import backend.tools.job_automation as job_automation

            job_automation.AUTOMATION_DIR = job_automation.Path(os.environ["DEXTER_JOB_AUTOMATION_DIR"])
            job_automation.CONFIG_PATH = job_automation.AUTOMATION_DIR / "automations.json"
            job_automation.RUNS_DIR = job_automation.Path(os.environ["DEXTER_JOB_AUTOMATION_RUNS_DIR"])

            setup = job_automation.job_automation_agent(
                action="setup",
                query="find latest 2027 Software Engineer Internships for CS students",
                automation_id="test_morning_jobs",
                time="08:30",
                install_launch_agent=False,
            )
            status = job_automation.job_automation_agent(action="status")

        self.assertTrue(setup["ok"])
        self.assertIn("test_morning_jobs", setup["output"])
        self.assertTrue(status["ok"])
        self.assertEqual(status["automations"][0]["id"], "test_morning_jobs")

    def test_send_resume_whatsapp_dry_run_uses_local_file(self):
        with TemporaryDirectory() as temp_dir:
            old_roots = os.environ.get("DEXTER_SAFE_FILE_ROOTS")
            os.environ["DEXTER_SAFE_FILE_ROOTS"] = temp_dir
            resume_path = os.path.join(temp_dir, "Vishal Resume.pdf")
            with open(resume_path, "wb") as file:
                file.write(b"%PDF-1.4\n")

            try:
                result = send_resume_whatsapp(
                    receiver="dad",
                    file_path=resume_path,
                    dry_run=True,
                )
            finally:
                if old_roots is None:
                    os.environ.pop("DEXTER_SAFE_FILE_ROOTS", None)
                else:
                    os.environ["DEXTER_SAFE_FILE_ROOTS"] = old_roots

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "dry_run")
        self.assertFalse(result["sent"])
        self.assertEqual(result["selected_resume"]["name"], "Vishal Resume.pdf")

    def test_send_resume_whatsapp_uses_browser_contact_name(self):
        import backend.tools.browser_agent as browser_agent

        with TemporaryDirectory() as temp_dir:
            old_roots = os.environ.get("DEXTER_SAFE_FILE_ROOTS")
            os.environ["DEXTER_SAFE_FILE_ROOTS"] = temp_dir
            resume_path = os.path.join(temp_dir, "Vishal Resume.pdf")
            with open(resume_path, "wb") as file:
                file.write(b"%PDF-1.4\n")

            calls = []
            original = browser_agent.send_whatsapp_file_via_brave

            def fake_send_whatsapp_file_via_brave(
                phone="",
                file_path="",
                caption="",
                receiver="",
                auto_send=True,
                timeout_seconds=75,
            ):
                calls.append(
                    {
                        "phone": phone,
                        "file_path": file_path,
                        "caption": caption,
                        "receiver": receiver,
                        "auto_send": auto_send,
                    }
                )
                return {
                    "ok": True,
                    "tool": "browser_agent",
                    "platform": "whatsapp",
                    "status": "drafted",
                    "sent": False,
                    "output": "Attached resume draft.",
                }

            browser_agent.send_whatsapp_file_via_brave = fake_send_whatsapp_file_via_brave
            try:
                result = send_resume_whatsapp(
                    receiver="my dad",
                    file_path=resume_path,
                    auto_send=False,
                )
            finally:
                browser_agent.send_whatsapp_file_via_brave = original
                if old_roots is None:
                    os.environ.pop("DEXTER_SAFE_FILE_ROOTS", None)
                else:
                    os.environ["DEXTER_SAFE_FILE_ROOTS"] = old_roots

        self.assertTrue(result["ok"])
        self.assertEqual(calls[0]["phone"], "")
        self.assertEqual(calls[0]["receiver"], "my dad")
        self.assertEqual(calls[0]["caption"], "Here is my resume.")


if __name__ == "__main__":
    unittest.main()

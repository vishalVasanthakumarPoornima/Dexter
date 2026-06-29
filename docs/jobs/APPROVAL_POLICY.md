# Approval Policy

Jobs OS is not a spam bot.

Rules:

- Auto-submit is disabled.
- Every external application submission requires explicit approval.
- Restricted platforms are manual-only or supervised-link sources.
- Dexter never bypasses CAPTCHA, MFA, login, or anti-automation controls.
- Dexter never automatically answers legal, visa, demographic, disability, veteran, gender, or race questions.
- Application packets may suggest language, but must not fabricate experience.
- Supervised apply sessions fill only safe profile fields and stop before final submit.

The current `/api/jobs/{id}/submit-approved` endpoint intentionally returns an error unless a future source-specific policy explicitly enables submission.

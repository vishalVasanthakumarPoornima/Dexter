# Jobs OS Limitations

- Live source coverage depends on configured company tokens, API keys, and source availability.
- ATS-wide search is not possible for Greenhouse, Lever, Ashby, SmartRecruiters, or Recruitee without company identifiers; Dexter can call their public feeds once identifiers are configured.
- Careerjet, Jooble, and Brave Search are implemented but disabled by default until keys are configured.
- Web discovery currently creates review links rather than crawling search results directly.
- Browser apply sessions currently implement a safe fake-form vertical slice and field mapping summary. Real ATS fill flows should be added source by source.
- PDF resume parsing uses `pypdf` when available and can fail on image-only PDFs.
- WhatsApp/email reports are provider stubs unless credentials and transport are configured.
- Restricted boards remain manual-only.
- The scoring engine is transparent and deterministic; it is not a guarantee of hiring fit.

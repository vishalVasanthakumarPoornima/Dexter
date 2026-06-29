# Jobs OS Limitations

- Live source coverage depends on configured company tokens, API keys, and source availability.
- Web discovery currently creates review links rather than crawling search results directly.
- Browser apply sessions currently implement a safe fake-form vertical slice and field mapping summary. Real ATS fill flows should be added source by source.
- PDF resume parsing uses `pypdf` when available and can fail on image-only PDFs.
- WhatsApp/email reports are provider stubs unless credentials and transport are configured.
- Restricted boards remain manual-only.
- The scoring engine is transparent and deterministic; it is not a guarantee of hiring fit.

# Additional event image sources

Extend the existing bounded public-image worker to EventHi, Splash event subdomains,
Shefa program/event pages, and Funcheap event listings. Keep exact host/path and
image-CDN restrictions, title/date matching, manual precedence and all time limits.
EventHi exposes its event metadata through an anonymous API: validate the linked
slug, public/published state, title and Berkeley date before choosing its image.
For EventHi only, ignore the descriptive words “cannabis” and “show” when comparing
names; require the remaining titles to match using the existing conservative rule.
Other sources use JSON-LD Event data plus Open Graph artwork. Splash instead
uses declared JSON-LD images or assets matched by event ID and filename, because
its generated Open Graph cards can contain blank theme placeholders. Try the page's larger
Open Graph artwork after a structured-data thumbnail fails image validation.

Use verified manual selections for old listings whose original pages disappeared
or reject automated access. Record provenance and accurate alt text. Do not invent
artwork, imply a postponed event happened, or choose unrelated people from search.
Searches are research for this backfill; the scheduled job has no broad search API.

Approach chosen as an implementation decision: extend the current adapters instead
of introducing a headless browser into the five-minute scheduled job. Deleted pages
and absent event metadata must continue to fail gracefully. Full recovery of all
seven images depends on finding a verifiable surviving source.

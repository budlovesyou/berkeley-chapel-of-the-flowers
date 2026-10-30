# Automatic Event Images Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline; steps use checkboxes.

**Goal:** Find and publish suitable artwork automatically for new public events.
**Architecture:** A bounded subprocess enriches a manifest after the public ICS feed
has been verified. The renderer uses manual UID mappings first and automatic
occurrence mappings second. Failures do not block event publication.
**Tech Stack:** Python, HTMLParser, urllib, Pillow, existing GitHub Actions.
**Spec:** docs/superpowers/specs/2026-10-30-automatic-event-images-design.md

## Global Constraints

- Preserve manually selected artwork and public-only calendar behavior.
- Five occurrences per run; 45-second worker deadline; failed lookups retry in 24 hours.
- Only known public event platform URLs and image CDNs; validate every redirect.
- Page limit 2 MB, image limit 8 MB, 20 million pixels, output at most 1200x1200.

## Review Focus

- Reused series URLs: mismatched dates must not leak artwork to other occurrences.
- Redirects and oversized/non-image payloads: reject before storing.
- First bad source: continue to a second supported event link.
- Persist failed attempts before requests so a timed-out first item cannot starve later ones.
- Worker exceptions: public events still render with previously saved manual images.

### Task 1: Discovery and publication

**Files:** Create scripts/event_images.py and test/test_event_images.py; modify
scripts/calendar_feed.py, requirements-events.txt, .github/workflows/update-events.yml,
and assets/event-images/README.md.

**Interfaces:** `image_key(event)` identifies an occurrence; `fingerprint(event)`
identifies lookup input; `discover(events, root, now, reader)` writes manifest/assets;
`run_discovery(events, root)` runs the bounded worker; `load_images(events, root)`
returns manual UID and eligible automatic occurrence mappings for the renderer.

- [x] Write failing metadata tests for Eventbrite JSON-LD, Partiful/Luma embedded
  public-page data, wrong titles/dates, multiple JSON-LD events and unsafe URLs.
- [x] Implement extraction and bounded fetching with redirect checks and image decoding.
- [x] Write failing discovery tests for retries, changed links, source failure,
  manual precedence, recurrence isolation, invalid images, and worker failure.
- [x] Implement persistence and occurrence selection; wire the opt-in CLI flag to
  the existing workflow and include generated manifest/assets in its commit.
- [x] Run the full unittest suite and an isolated live-event discovery smoke test.
- [x] Review the complete change, commit, and publish only with applicable authorization.

## Verification

All 37 unittest cases passed. An isolated live smoke test saved and decoded artwork
from real Eventbrite, Partiful, and Luma pages. A subsequent subprocess run retained
all three cached selections without new requests. Independent code review approved
the change with no blocking findings. Publication status is recorded in Git history
and the calendar workflow run.

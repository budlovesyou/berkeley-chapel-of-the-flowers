# Additional Image Sources Implementation Plan

> Use superpowers:executing-plans inline; request one fresh final code review.

**Goal:** Expand automatic image lookup and backfill the seven remaining listings wherever verified artwork survives.
**Architecture:** Add constrained hosts/CDNs and an EventHi public API adapter to the existing worker. Keep manual provenance for researched historical images.
**Tech Stack:** Existing Python urllib/HTMLParser/Pillow worker and unittest suite.
**Spec:** docs/superpowers/specs/2026-10-30-additional-image-sources-design.md

## Constraints and review focus
- Keep 45-second worker deadline, five-occurrence batches, and 24-hour retries.
- Reject spoofed domains, arbitrary API paths and unrelated/private EventHi records.
- Check Berkeley local date across UTC boundaries; retain title and event ID checks.
- Do not allow a tiny thumbnail to hide a usable larger event image.
- Keep manual choices and postponed labels unchanged; check every backfill visually.

## Task 1: Support, backfill and publish
- [x] Add failing tests in test/test_event_images.py for new source extraction,
      API selection, private/wrong-ID/wrong-date rejection and thumbnail fallback.
- [x] Extend scripts/event_images.py with the new allowlists and source_candidates(link,event,reader).
- [x] Run all tests and a live EventHi lookup against the real unpictured event.
- [x] Save verified historical images, source URLs and descriptive alt text in event-images.json.
- [x] Document limits, review the diff, render the full calendar, test and publish.

## Evidence

43 unittest cases pass. New source tests first failed before implementation. Live
EventHi discovery fetched and decoded the real February 13 Dime Bag image. Six
other historical occurrences received visually verified manual selections, with
source URLs, guide/portrait alt text and selection notes. Full rendering has 109
cards and 109 images; all titles, including POSTPONED, remain unchanged. Independent
code review approved with no blocking findings. Direct test-script entrypoint was
moved after all classes; Dime Bag alt text describes its actual venue image.

Residual limit: page-level Open Graph artwork is trusted after event metadata
matches. A source publishing unrelated artwork or ambiguous multi-event metadata
can still require manual review. Deleted or blocked sources require manual picks.

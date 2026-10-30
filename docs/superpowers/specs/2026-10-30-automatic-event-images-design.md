# Automatic event images

The user requested automatic image discovery when events enter the public calendar.
Extend the existing 15-minute publishing job. The calendar alone defines public
listings. Preserve every manually selected image, including Community Survival.

Implementation decisions: discover from linked Eventbrite, Partiful and Luma event
pages and their image CDNs. Require matching event name and Berkeley calendar date
from structured event data; use the matching event image or page Open Graph image.
Do not guess from general web image search or fetch unrelated organizer homepages.
Use per-occurrence mappings so reused ticket links cannot apply a dated poster to
other dates. Missing links, blocked pages and uncertain matches remain text cards.

Save bounded, decoded, optimized local WebP assets and provenance. Cache failed
attempts for 24 hours; a changed title, date or link triggers a fresh attempt. Limit
each refresh to five occurrences and give the worker 45 seconds total. The parent
still renders/publishes the calendar if the worker fails. Retain successful results
across runs by committing the image manifest and assets in the existing workflow.

Alternative: general web searches would need another service and weaker matching.
Alternative: fetching on visitors' browsers creates fragile third-party requests.
This implementation uses deterministic event-page metadata during publication.

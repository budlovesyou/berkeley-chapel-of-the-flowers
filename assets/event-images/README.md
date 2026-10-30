# Event artwork

`event-images.json` maps the public Google Calendar UID to verified local artwork.
The calendar remains the source of event titles, times, descriptions, and links.
Image metadata never creates a listing or publishes a private calendar event.

For a new event, find artwork on its public ticket or organizer page, verify the
actual event/series (including any dates printed on a flyer), and save an optimized
WebP here. Use a lowercase filename containing only letters, digits, and hyphens.
Add its `src`, intrinsic `width` and `height`, descriptive `alt`, `source_url`,
`original_url`, and `verified_on` to the manifest under the event's exact UID.
Recurring occurrences with the same UID share artwork; use an undated series photo
when a dated poster would be misleading. Do not match solely by event title.

The page generator reads the manifest on every scheduled refresh. Unmatched events
and missing image files remain normal text cards. Images are served locally,
lazy-loaded, displayed without cropping, and linked to a larger view. Visitors make
no third-party image requests. Automatic discovery at publication time is described
below.

Sources verified October 30, 2026: public Eventbrite and Partiful listings, Luma,
the linked Phipps Pt. Bandcamp album, bud.com's event page, and existing Chapel
photography of Singing the Great Turning. Each image's source is in the manifest.
Community Survival Program listings use the undated Chapel gathering photo from
the BPPALN holistic-health program gallery, selected by Justin on October 30, 2026.
The 23 exact event UIDs cover the historical listings and ongoing monthly series.

No verified artwork was found for the remaining Shefa, Cannabis Author Showcase, Dime Bag, postponed Fantasy Waltz, and Richard Lee
memorial listings; they deliberately retain their text presentation.

## Automatic discovery

The scheduled `calendar_feed.py --discover-images` run also checks public Eventbrite,
Partiful, and Luma event links for missing images. It requires matching event titles
and dates from the page's structured data. A linked organizer homepage, missing date,
blocked page, or uncertain match leaves the listing without automatically chosen
artwork. No general web search service, API key, or paid image service is used.

Automatic images live under `occurrences` in `event-images.json`, keyed by calendar
UID and start time. A changed title/date/link invalidates the automatic selection;
manual entries under `events` always take precedence, including across recurring
occurrences. Shared series landing pages spanning more than seven days are skipped
because they may show a different date's flyer.

Each refresh attempts at most five missing occurrences, prioritizing upcoming
events. Failed attempts are recorded under `attempts` and retry after 24 hours;
changed inputs retry immediately. The worker has a 45-second total deadline and
five-second socket timeouts. A failure or timeout still allows calendar publication.
The next scheduled run continues with other eligible events.

Only HTTPS event platform URLs and their known image CDNs are fetched, including
on redirects. Responses are bounded (2 MB HTML / 8 MB images); raster images are
decoded, limited to 20 megapixels, and saved as WebP at most 1200 pixels per side.
The workflow commits the manifest and new assets together with the generated page.
Original source URLs and discovery dates are retained in each automatic entry.
Run `python -m unittest discover -s test` to verify the behavior.

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
lazy-loaded, displayed without cropping, and linked to a larger view. There are no
third-party image requests or image-search dependencies in the publishing job.

Sources verified October 30, 2026: public Eventbrite and Partiful listings, Luma,
the linked Phipps Pt. Bandcamp album, bud.com's event page, and existing Chapel
photography of Singing the Great Turning. Each image's source is in the manifest.
Community Survival Program listings use the undated Chapel gathering photo from
the BPPALN holistic-health program gallery, selected by Justin on October 30, 2026.
The 23 exact event UIDs cover the historical listings and ongoing monthly series.

No verified artwork was found for the remaining Shefa, Cannabis Author Showcase, Dime Bag, postponed Fantasy Waltz, and Richard Lee
memorial listings; they deliberately retain their text presentation.

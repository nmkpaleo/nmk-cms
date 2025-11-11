# Accession detail

The accession detail page provides a comprehensive overview of a single accession record. It is built on the shared W3.CSS template (`base_generic.html`) and adapts to the viewport size so the most important information stays visible.

## Layout overview

- **Upper grid (large screens):** The page splits the header card into two columns. The upper left card shows the Accession overview while the upper right column stacks Specimen details, Related field slips (preview mode), and Horizon information. On tablets and phones these sections collapse into a single column in the same order.
- **Lower region:** References, Media, and Comments occupy the lower half of the page. They remain stacked vertically in the order listed so long tables continue to scroll independently of the summary content.
- **Action buttons:** Management buttons (for example **Add specimen**, **Add reference**, **Add comment**) remain aligned with their headings and continue to honour the existing permission checks for collection managers and superusers.

## Media hover preview

- Hovering or focusing the thumbnail in the Media table now opens a large preview panel. On large screens the panel centres itself and doubles the preview width (up to 720&nbsp;px) so curators can read labels without leaving the page.
- On smaller screens the panel follows the pointer and keeps within the viewport edges. Touch users can tap once to open the full image in a new tab, just like before.
- Keyboard users can Tab to the thumbnail links; the preview opens on focus and closes on blur or <kbd>Escape</kbd>. The image retains the original alt text for screen readers.

## Related workflows

- The Comments table and the field slip management modal behave as before. The new layout simply gives more room to the upper summary cards while leaving forms and modals untouched.
- If you need to download a media asset, continue to use the thumbnail link. The hover preview is read-only and does not replace the existing download behaviour.
- Use the **Print specimen card** button in the accession row header to open a compact, print-ready card. The card groups taxonomy (Family, Subfamily, Tribe, Genus, Species), specimen element details (Element, Side, Portion, Condition, Fragments), locality/site information, and accession/field numbers into a bordered layout that mirrors the in-app detail view.
- When an identification only includes a free-text taxon, the print layout automatically fills the taxonomy table with the resolved family, subfamily, tribe, genus, and species—matching what you see in the accession detail view—so nothing prints blank.
- The print window includes its own **Print** button and launches in a new tab (`target="_blank"`) so you can keep the accession page open while sending the card to paper or PDF.

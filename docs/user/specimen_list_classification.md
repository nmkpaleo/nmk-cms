# Specimen list page classification

## Overview
Specimen list pages are classified before extraction so pages can be routed to the right workflow. Pages identified as specimen lists move into the row-extraction review flow, while other page types are routed to a text-only view.

## Page types
- **Specimen list**: Handwritten list with tabular rows.
- **Handwritten text**: Narrative handwritten notes without row structure.
- **Typewritten text**: Typed pages that are not specimen lists.
- **Other**: Maps, drawings, or non-textual pages.

## How routing works
- **Specimen list** pages go to the review queue for row extraction.
- **Non-specimen** pages display as text-only views for searchable OCR content.

## Classification status
- **Pending**: Awaiting classification.
- **Classified**: Classification completed with a page type and confidence score.
- **Failed**: Classification attempt failed and should be requeued.

## Troubleshooting
- If a page stays pending, confirm the classification job is running.
- For failed pages, requeue classification from the admin list and verify the page image exists.

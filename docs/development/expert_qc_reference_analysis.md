# Expert QC Reference Handling Analysis

## Scope
Task T1: confirm expert QC references use the shared formset/controller and identify any visibility issues for the delete control.

## Findings
- The expert QC view (`MediaExpertQCWizard`) injects the `reference_formset` from `MediaQCFormManager` into the template context alongside other QC formsets, ensuring the expert flow receives the same reference data as other wizards.【F:app/cms/views.py†L3650-L3685】
- The expert wizard template extends `wizard_base.html`, which renders the References section, including the `reference_formset` management form and per-reference cards via the shared `cms/qc/partials/reference_card.html` partial that already contains the "Delete reference" button tied to the formset DELETE flag.【F:app/cms/templates/cms/qc/wizard_base.html†L548-L666】【F:app/cms/templates/cms/qc/partials/reference_card.html†L1-L40】
- `wizard_base.html` always loads the `qc_references_controller.js` Stimulus controller and registers it when present, so the expert route initializes the same delete/restore interactions and empty-state logic as other QC flows; no expert-specific omission was found.【F:app/cms/templates/cms/qc/wizard_base.html†L734-L899】

## Conclusion
The expert QC route already uses the shared reference formset, partial, and Stimulus controller. The "Delete reference" control is present and wired to set the formset DELETE flag for each reference card, with no visibility conditions specific to the expert flow observed in templates or scripts.

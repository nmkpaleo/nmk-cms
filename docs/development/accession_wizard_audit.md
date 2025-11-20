# Accession Wizard Audit

## Scope
Audit of the `/accession-wizard/` flow to understand how `specimen_no` is set and rendered, focusing on form usage and the template structure in `app/cms/templates/cms/accession_wizard.html`.

## Wizard Steps and Data Flow
- **Step 0 – Accession number selection**: `AccessionNumberSelectForm` exposes an `accession_number` choice field populated from the `available_numbers` kwarg injected via `AccessionWizard.get_form_kwargs`. This derives up to 10 unused numbers from the active `AccessionNumberSeries` for the logged-in user. Selected value is submitted through the hidden input `0-accession_number`.【F:app/cms/forms.py†L184-L191】【F:app/cms/views.py†L1868-L1891】【F:app/cms/templates/cms/accession_wizard.html†L11-L23】
- **Step 1 – Accession details**: `AccessionForm` includes `specimen_no` alongside `collection`, `specimen_prefix`, `accessioned_by`, `type_status`, and `comment`. `AccessionWizard.get_form_initial` pulls `accession_number` from step 0 into the `specimen_no` initial value when rendering this step.【F:app/cms/forms.py†L565-L583】【F:app/cms/views.py†L1893-L1906】
- **Step 2 – Specimen composite**: When present, `get_form_initial` also rehydrates `specimen_no` for this step from step 1 data, ensuring consistency if later logic depends on it.【F:app/cms/views.py†L1906-L1911】

## Persistence
- In `AccessionWizard.done`, `specimen_no` on the created `Accession` instance is explicitly set from `accession_number` captured in step 0, not from user-editable form data. This prevents divergence between the selected number and saved accession value during finalization.【F:app/cms/views.py†L1931-L1965】

## Template Rendering
- The template iterates through `wizard.form` fields and renders visible fields with a label and widget inside W3.CSS-styled containers. Hidden fields are emitted directly. On step 1, `specimen_no` is rendered as display-only text with a hidden field so the value remains visible but cannot be edited.【F:app/cms/templates/cms/accession_wizard.html†L35-L71】
- Step 0 uses a link list for number selection and sets the hidden input before submission. Subsequent steps use a multipart `<form>` with CSRF, management form, navigation buttons, and DAL initialization script to activate autocomplete widgets.【F:app/cms/templates/cms/accession_wizard.html†L11-L57】【F:app/cms/templates/cms/accession_wizard.html†L59-L93】

## Observations
- The wizard now prevents edits to `specimen_no` by showing the selected accession number as read-only text and resubmitting it through a hidden field. Users must return to the first step to choose a different number instead of modifying the value mid-flow.
- The persisted value continues to come from `accession_number` stored in step 0, keeping the selected number in sync with the final accession record.


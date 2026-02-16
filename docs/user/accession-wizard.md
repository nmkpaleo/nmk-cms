# Accession Wizard

The accession wizard walks collection managers through selecting a specimen number and filling in the accession details. It uses the shared W3.CSS card layout so steps are mobile-friendly and consistent with other CMS forms.

## Steps

1. **Select an accession number** – Choose a number from your active accession number series. The list is limited to the next available numbers for your account. Submitting the step stores the selection for the rest of the wizard.
2. **Enter accession details** – The chosen specimen number appears as display-only text and is saved through a hidden field. If you need to pick a different number, return to step 0 rather than editing the value in the browser tools.
3. **Add specimen data** – Complete any remaining specimen, identification, or related records as prompted by the wizard. Navigation buttons let you move backward without losing previously entered data.

## Tips

- The wizard keeps your selected specimen number in sync with the accession record even if later fields are changed or tampered with. Use the provided navigation buttons to revisit earlier steps instead of manually editing the value.
- Autocomplete fields load after the page finishes rendering; if a dropdown looks empty, wait a moment for the DAL widgets to initialise.

# Authentication Experience

The public login, signup, and password management screens now share the same W3.CSS layout used across the CMS.

## What to expect

- **Hero layout** – Every auth page renders inside a two-column card with the NMK skull artwork so the experience matches the main site branding.
- **W3.CSS controls** – Input fields, buttons, and system messages inherit the CMS typography and colors by default. There is no need to memorize custom class names when building new auth snippets.
- **ORCID support** – An "Sign in with ORCID" button appears whenever the ORCID provider is configured in django-allauth. The button uses the bundled `orcid-logo.png` asset for consistent branding.
- **Accessibility** – Landmark tags (`<section>`, `<article>`, `<aside>`) and ARIA labels are already present. Keep these intact when adding new copy so screen readers continue to describe the layout correctly.

## Troubleshooting

1. If the layout looks unstyled, confirm the CDN-hosted W3.CSS stylesheet is reachable from your network. The `<head>` of the page should contain `https://www.w3schools.com/w3css/4/w3.css`.
2. If the ORCID button is missing, ensure the ORCID provider is enabled in `INSTALLED_APPS` and a Social Application entry is linked to the default Site in Django admin.
3. When editing templates, rely on the `_auth_layout.html` partial to avoid duplicating markup—only the `auth_layout_title`, `auth_layout_subtitle`, and `auth_layout_body_template` context values should change per view.

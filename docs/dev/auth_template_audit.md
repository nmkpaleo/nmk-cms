# Account Template Audit

_Last updated: 2024-08-14_

## Layout hierarchy

- `app/templates/account/base_entrance.html` extends `allauth/layouts/entrance.html`, which in turn extends `allauth/layouts/base.html`.
- `app/templates/account/base_manage*.html` (including `base_manage.html`, `base_manage_email.html`, `base_manage_password.html`, and `base_reauthenticate.html`) all extend `allauth/layouts/manage.html`, which also inherits from `allauth/layouts/base.html`.
- `allauth/layouts/base.html` loads the project stylesheet (`{% static 'css/style.css' %}`) and Font Awesome 6 via CDN. **W3.CSS is _not_ loaded** by default here, so templates that use `w3-*` classes rely on other base templates or must add the stylesheet explicitly.
- `app/cms/templates/base_generic.html` (used by most CMS pages) loads W3.CSS from the official CDN. The auth templates currently bypass `base_generic.html`, so they miss that import.

## Template inventory (accounts)

| Template | Base | Notable blocks | Inputs/context assumptions |
| --- | --- | --- | --- |
| `account/login.html` | `account/base_entrance.html` | Overrides `head_title`, `content`, `extra_body`. Uses semantic `<section>`, `<article>`, `<header>` wrappers with `w3-` classes and Font Awesome icon. | Expects `SOCIALACCOUNT_ONLY`, `SOCIALACCOUNT_ENABLED`, `LOGIN_BY_CODE_ENABLED`, `PASSKEY_LOGIN_ENABLED`, `request_login_code_url`, `signup_url`, `redirect_field`, `PASSKEY_LOGIN_ENABLED`, `PASSKEY_LOGIN_ENABLED`, and `mfa_login` form id. Includes `socialaccount/snippets/login.html` for provider buttons. |
| `account/signup.html` | `account/base_entrance.html` | Similar layout to login with W3.CSS hero card. | Uses `SOCIALACCOUNT_ONLY`, `SOCIALACCOUNT_ENABLED`, `PASSKEY_SIGNUP_ENABLED`, `signup_by_passkey_url`, `login_url`, `redirect_field`. |
| `account/logout.html` | `account/base_manage.html` | Plain headings/forms, no W3 wrappers yet. | Needs `account_logout` URL and `redirect_field`. Uses `allauth` element tags for form/button. |
| `account/password_reset.html` | `account/base_entrance.html` | Basic heading & paragraphs (no W3 structure yet). | Requires `user`, `form`, `reset_url`. Includes snippet `account/snippets/already_logged_in.html` when `user.is_authenticated`. |
| `account/password_reset_done.html`, `password_reset_from_key.html`, `password_reset_from_key_done.html`, `password_change.html`, `password_set.html` | `account/base_entrance.html` or `base_manage_password.html` depending on flow. | All rely on `allauth` element tags and mostly unstyled markup. None currently reference W3 utility classes. | Expect `token_fail`, `form`, `action_url`, `login_url`, `password_change_url`, etc. |
| `account/request_login_code.html` & `confirm_login_code.html` | `account/base_entrance.html` | Use `element form` components, currently lacking W3 layout wrappers. | Require `redirect_field`, `login_url`, `FORM_NAME`, and bool flags for passkey or login-by-code toggles. |
| `account/reauthenticate.html`, `account/base_reauthenticate.html` | Manage layout | Manage flows for sensitive ops; no W3 structure yet. | Expect `form`, `redirect_field`. |
| `account/messages/*.html` | `base_manage.html` | Provide `django.contrib.messages` wrappers; no W3 classes yet. | Rely on `message` context entries. |

## Social account snippets

- `socialaccount/snippets/login.html` provides the "Or sign in with" divider plus provider list, using W3 utility classes for spacing and borders.
- `socialaccount/snippets/provider_list.html` loops through `socialaccount_providers`. Each provider button is rendered via `{% element provider %}`, so styling is derived from django-allauth defaults unless overridden.

## Static assets

- `animal_skull.png` lives at `app/cms/static/images/animal_skull.png`. It is only referenced in `app/cms/templates/index.html` today and never appears on any auth template.
- The shared stylesheet for the site is `app/cms/static/css/style.css`. It defines navigation helpers, Select2 overrides, accessibility utilities, and general layout tweaks but **does not provide W3.CSS base classes**.

## Key findings

1. **W3.CSS availability gap**: Because the auth templates extend `allauth/layouts/base.html` instead of `cms/base_generic.html`, they never import `https://www.w3schools.com/w3css/4/w3.css`. Existing `w3-` classes therefore render unstyled unless the browser still has cached W3 styles from other views. We need to add an explicit W3.CSS `<link>` for entrance/manage layouts before investing more in W3-based design.
2. **Layout consistency**: Only `login.html` and `signup.html` currently use semantic `<section>`/`<article>` wrappers with W3 utility classes. Logout, password reset, and passkey/code templates still rely on the default allauth markup, so they will need structural work to match the new visual direction.
3. **ORCID integration**: No template references ORCID or its logo yet. Social providers are driven entirely by `socialaccount/snippets/provider_list.html`, so to highlight ORCID we will either need a custom provider-specific button or an additional CTA that targets the `orcid` provider id.
4. **Hero imagery**: `animal_skull.png` is unused outside of the marketing home page. Introducing it on auth views will require referencing `{% static 'images/animal_skull.png' %}` and probably adding responsive containers because the current card layout does not account for imagery.
5. **Translation coverage**: Nearly all strings within the auth templates are already wrapped with `{% trans %}`/`{% blocktranslate %}`. Any new copy introduced for ORCID or the skull hero must maintain that coverage.

## Recommendations for subsequent tasks

- Update `allauth/layouts/base.html` (or override via `extra_head`) to load W3.CSS alongside the existing project stylesheet so that entrance/manage flows consistently inherit the framework.
- Create a reusable partial for the auth hero layout to avoid duplicating the W3 container markup and to centralize the skull image usage.
- Extend `socialaccount` snippets or inject a dedicated ORCID login button with the official logo to satisfy branding requirements.
- Ensure any additional imagery or CDN assets comply with the project's Content Security Policy and are declared in the deployment manifests if needed.

## Regression tests

- `tests/accounts/test_auth_templates.py` confirms the login page renders the shared hero (`w3-container w3-padding-64 w3-sand`) and the skull artwork.
- The same module verifies the ORCID CTA appears with the branded `orcid-logo.png` asset and `w3-button w3-green` styling to guard against accidental markup regressions.

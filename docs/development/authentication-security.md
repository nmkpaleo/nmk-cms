# Authentication security

The application uses allauth for local-password and ORCID authentication.

## Controls

- Ordinary public signup is closed. Administrators create local users; ORCID may create a linked account.
- Login and password-reset forms use server-side CAPTCHA when `RECAPTCHA_PUBLIC_KEY` and `RECAPTCHA_PRIVATE_KEY` are configured.
- Login and password-reset submissions are rate-limited per client address by Django’s cache. Defaults are 10 attempts per 15 minutes; configure `AUTH_RATE_LIMIT_MAX_ATTEMPTS`, `AUTH_RATE_LIMIT_LOG_THRESHOLD`, and `AUTH_RATE_LIMIT_WINDOW_SECONDS` as needed.
- Allauth’s password-reset flow must retain its generic completion response so it does not disclose whether an address is registered.
- Security warnings are emitted through the `security.auth` logger when repeated attempts or a limit breach occurs.

## Reverse-proxy requirement

Configure equivalent or stricter rate limits at the production reverse proxy/WAF for:

- `POST /accounts/login/`
- `POST /accounts/password/reset/`
- Any login-code or passwordless sign-in request endpoints enabled by allauth

The Django cache limiter is defense in depth. Use a shared production cache (for example Redis) so limits apply across application workers. Do not trust `X-Forwarded-For` unless the proxy overwrites it and is the only public path to the application.

## Verification

Unauthenticated password-change requests must be redirected to login and must not change an account. Password-change POSTs must continue to include Django’s CSRF token and allauth’s current-password validation.

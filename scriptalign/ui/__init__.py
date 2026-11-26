"""Desktop UI: a local server plus a single-page frontend.

The server binds to localhost only and requires a per-session token on every
mutating request, so another web page cannot drive the app.
"""

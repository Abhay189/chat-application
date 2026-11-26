"""Production WSGI entry point. Put an HTTPS reverse proxy in front of it."""
import os
from waitress import serve
from app import app

if __name__ == "__main__":
    options = dict(host="127.0.0.1", port=int(os.getenv("PORT", "5000")),
        threads=8, connection_limit=100, max_request_body_size=7 * 1024 * 1024,
        max_request_header_size=32768, channel_timeout=60)
    if os.getenv("TRUST_LOCAL_PROXY") == "1":
        # Only enable with a local proxy that overwrites forwarded headers.
        options.update(trusted_proxy="127.0.0.1", trusted_proxy_count=1,
            trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto", "x-forwarded-host"})
    serve(app, **options)

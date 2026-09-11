# Runtime TLS certificates

Place `cert.pem` and `key.pem` here only on the deployment host, or set `TLS_CERTS_DIR=/absolute/path/to/certs` to mount them from another runtime-only directory.

Required filenames for `nginx-tls.conf`:

- `cert.pem` — public certificate
- `key.pem` — private key

Do not commit PEM files. The previously tracked key must be treated as compromised and replaced before production use.

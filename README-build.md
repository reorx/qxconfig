# build-qxconf

Turn a Quantumult X profile into a **self-contained directory** that no longer
depends on external rule links or node subscriptions.

It does two things:

1. **Localizes remote rules.** Every live URL in `[filter_remote]` and
   `[rewrite_remote]` is downloaded into the output directory (mirroring its
   host + path under `rules/` and `rewrites/`), and the URL in the config is
   rewritten to `<base-url>/<local-path>`. Serve the output directory with any
   static HTTP server and Quantumult X fetches the rules from there.
2. **Injects nodes.** Proxies from a Clash config are converted into
   `[server_local]` entries (`ss` incl. `obfs`, `trojan`, `anytls`). Existing
   region policies keep working via their `server-tag-regex`.

Disabled lines (`enabled=false` or commented with `;`/`#`) are left untouched
and never downloaded. Unsupported proxy types/plugins (e.g. `shadow-tls`) are
skipped and reported instead of producing broken nodes.

Rules already present in the output directory are reused; pass `--force` to
re-download them. Pass `--disable-rewrite-remote` or `--disable-task-local` to
exclude those sections entirely (header, body, and the section's own descriptive
comment are removed; the next section's leading comment is preserved).

With `--server-remote [TAG]` the nodes are not converted; instead the Clash
config is copied to `<output>/clash/` and referenced as a `[server_remote]`
subscription (`<base-url>/clash/<file>`), letting Quantumult X parse it on its
side. `TAG` defaults to `lan`. Example output line:

```
[server_remote]
http://192.168.1.140:8888/clash/local-unified.yaml tag=lan, update-interval=172800, opt-parser=true, enabled=true
```

## Usage

```bash
uv run build-qxconf.py \
  --source profile/QX_Config.conf \
  --base-url 'http://192.168.1.140:8888' \
  --clash-nodes ../clash_config/build/local-unified/local-unified.yaml \
  -o dest
```

Then serve it:

```bash
python -m http.server 8888 --directory dest
```

## Develop

```bash
uv sync
uv run pytest
```

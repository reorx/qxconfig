# qxconfig

Builds a self-contained Quantumult X profile directory (`dest/`) from a source
profile + a Clash node config. See `README-build.md` for details.

## Working rules

- **Always run `./build.sh` after completing a change.** The user consumes the
  built output in `dest/`, not the source. An unbuilt change leaves stale or
  broken output. Confirm `dest/QX_Config.conf` after building.
- **Treat `qxconf/sample.conf` as the official Quantumult X spec.** It is the
  upstream sample config; use it as the source of truth when checking syntax or
  reviewing generated output.

## Quantumult X syntax notes

- Remote-resource lines in `[server_remote]`, `[filter_remote]`, and
  `[rewrite_remote]` use the URL as the **first comma-separated field**:
  `URL, tag=..., ...`. A space before `tag=` is invalid and QX rejects it on
  import.
- In `[dns]`, when `doh-server`/`doq-server` is set, plain non-domain-bound
  `server =` lines are ignored; only domain-bound ones (`server = /*.x.com/...`)
  still apply.

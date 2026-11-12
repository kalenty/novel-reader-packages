# Novel Reader — Termux packages

This repository distributes signed Android ARM64 packages. Application source code remains private. Only the **testing** channel is available; device installation and legacy upgrade acceptance remain pending. No stable release is implied.

## Trust and installation

Primary signing fingerprint:

`4A5257DA36C1DD201DD5725A7D02DF8EE817027D`

The signing private key is not held by GitHub. Compare this full fingerprint with the one provided by the maintainer through a separate trusted channel before trusting the repository.

In Termux, install prerequisites and download the public key (no remote script is executed):

```sh
pkg install curl gnupg
mkdir -p "$PREFIX/etc/apt/keyrings"
curl --fail --location --proto '=https' --proto-redir '=https' https://kalenty.github.io/novel-reader-packages/novel-reader.asc -o "$PREFIX/etc/apt/keyrings/novel-reader.asc"
gpg --show-keys --with-fingerprint "$PREFIX/etc/apt/keyrings/novel-reader.asc"
```

After verifying the fingerprint, configure the scoped key and repository:

```sh
printf 'deb [arch=aarch64 signed-by=%s/etc/apt/keyrings/novel-reader.asc] https://kalenty.github.io/novel-reader-packages testing main\n' "$PREFIX" > "$PREFIX/etc/apt/sources.list.d/novel-reader.list"
cat > "$PREFIX/etc/apt/preferences.d/novel-reader" <<'PINS'
Package: novel-reader
Pin: origin "kalenty.github.io"
Pin-Priority: 500

Package: *
Pin: origin "kalenty.github.io"
Pin-Priority: -1
PINS
pkg update
pkg install novel-reader
```

Only `novel-reader` is eligible from this source. Do not disable signature checks with `trusted=yes` or `--allow-unauthenticated`.

Before upgrading an existing installation: stop the server, back up the complete data directory and keep the previous installer. This source does not overwrite databases or automatically restart services. A package update does not prove data rollback compatibility. If the installed package has a higher Debian version, do not force a downgrade to this candidate.

After installation, `novel-reader version`, then `novel-reader start` (or restart a stopped existing installation).

## Publication and limits

The site bundle is reviewed and signed locally, then retained as a prerelease asset. Pages verifies the pinned fingerprint, bundle hash, repository signature, index hashes and package checksum before deployment. It has no signing secret or cross-repository write token.

Release metadata expires after 90 days. Expired or invalid metadata must fail closed; contact the maintainer to renew it. Old prerelease assets remain available for diagnosis and deliberate rollback. Third-party licenses are included inside each package. Go/JavaScript security scanners do not prove absence of C/C++ or unknown vulnerabilities.

No application source archive, account credentials, cookies, private books or build logs are published here. Frontend JavaScript and binary dependency metadata remain inspectable as with any distributed Web application.

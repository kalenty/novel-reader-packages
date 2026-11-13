# Novel Reader — Termux packages

This repository distributes signed Android ARM64 packages. Application source code remains private. The initial **testing** channel is available; device installation and legacy upgrade acceptance remain pending. Prerelease application versions enter testing automatically. Stable is created only when the maintainer submits a non-prerelease version after acceptance; no current stable release is implied.

## Termux 一键安装与更新

适用于标准 Termux 的 Android ARM64。在 Termux 执行这一条命令即可：

```sh
pkg install -y curl && curl -fsSL https://raw.githubusercontent.com/kalenty/novel-reader-packages/a54357510781645da9e71a05ef53332d40075c14/install.sh | bash
```

脚本自动验证软件源公钥、配置独立软件源、安装并启动阅读器。完成后可[打开阅读器](http://127.0.0.1:8080/)。以后也可重新执行同一命令检查更新。

升级时先下载软件包，再停止服务并备份数据；安装器自己的备份默认保留最近两份，位于 `~/.local/share/novel-reader-installer/`。安装失败不会自动覆盖数据库，日志也保存在此目录。不改动 Termux 的其他软件源。

当前默认 **testing** 通道；已配置的通道会保留，不强制降级。远程脚本固定在可审查的提交，软件包仍由 APT 验签。完整安装升级与回滚尚待 Android 真机验收。

<details>
<summary>手动配置、更新与排错</summary>

## Termux 安装与更新（独立软件源）

适用于标准 Termux 的 Android ARM64（`dpkg --print-architecture` 应显示 `aarch64`）。**手动安装过 `.deb` 不会自动添加软件源**；首次使用 `pkg` 更新时，需要完成下面的一次性配置。它与 Termux 国内镜像独立，不需要等待国内镜像同步。

当前使用 **testing** 通道。真机升级和回滚仍待验收；现有版本高于候选版时不要强制降级。

### 1. 安装配置工具

```sh
pkg install curl gnupg
```

### 2. 验证公钥并添加软件源（只需一次）

主公钥指纹为 `4A5257DA36C1DD201DD5725A7D02DF8EE817027D`。下面的命令会自动核对完整指纹及证书数量，验证成功才保存公钥、添加软件源；不会执行下载的脚本，也不会关闭签名验证。

```sh
(
  set -eu
  : "${PREFIX:?请在 Termux 中执行}"
  mkdir -p "$PREFIX/etc/apt/keyrings" "$PREFIX/etc/apt/sources.list.d" "$PREFIX/etc/apt/preferences.d"
  reader_key=$(mktemp "$PREFIX/etc/apt/keyrings/novel-reader.XXXXXX")
  trap 'rm -f "$reader_key"' EXIT
  curl --fail --location --proto '=https' --proto-redir '=https' \
    https://kalenty.github.io/novel-reader-packages/novel-reader.asc -o "$reader_key"
  reader_key_info=$(gpg --batch --show-keys --with-colons "$reader_key" 2>/dev/null)
  reader_fingerprint=$(printf '%s\n' "$reader_key_info" | awk -F: '$1=="fpr" {print $10; exit}')
  reader_certificates=$(printf '%s\n' "$reader_key_info" | awk -F: '$1=="pub" {n++} END {print n+0}')
  if [ "$reader_fingerprint" != '4A5257DA36C1DD201DD5725A7D02DF8EE817027D' ] || [ "$reader_certificates" != 1 ]; then
    echo '公钥验证失败，未添加软件源。' >&2
    exit 1
  fi
  mv "$reader_key" "$PREFIX/etc/apt/keyrings/novel-reader.asc"
  printf 'deb [arch=aarch64 signed-by=%s/etc/apt/keyrings/novel-reader.asc] https://kalenty.github.io/novel-reader-packages testing main\n' "$PREFIX" \
    > "$PREFIX/etc/apt/sources.list.d/novel-reader.list"
  cat > "$PREFIX/etc/apt/preferences.d/novel-reader" <<'PINS'
Package: novel-reader
Pin: origin "kalenty.github.io"
Pin-Priority: 500

Package: *
Pin: origin "kalenty.github.io"
Pin-Priority: -1
PINS
  echo 'Novel Reader testing 软件源已配置。'
)
```

`signed-by` 将信任限定到这个软件源；优先级配置仅允许它提供 `novel-reader`，避免替换 Termux 的其他软件包。不要使用 `trusted=yes` 或 `--allow-unauthenticated`。

### 3. 首次安装

```sh
pkg update
apt-cache policy novel-reader
pkg install novel-reader
novel-reader version
novel-reader start
```

浏览器打开[本地阅读器](http://127.0.0.1:8080/)。首次运行创建管理员账号，没有预设密码。

### 以后更新已有安装

先停止服务，备份**完整数据目录**并保留旧安装包；默认目录为 `$HOME/.local/share/novel-reader`，设置过 `NOVEL_READER_DATA` 时以自定义目录为准。不要仅复制仍在运行的 SQLite 主文件。

```sh
novel-reader stop
# 在此备份完整数据目录，确认完成后再继续。
pkg update
apt-cache policy novel-reader
pkg install novel-reader
novel-reader version
novel-reader start
```

软件包更新不会自动重启正在运行的服务。

### 提示 already the newest version 时

```sh
dpkg-query -W -f='${Version}\n' novel-reader
apt-cache policy novel-reader
cat "$PREFIX/etc/apt/sources.list.d/novel-reader.list"
pkg update
```

- `policy` 应列出 `https://kalenty.github.io/novel-reader-packages` 和候选版本；未出现时检查源文件及 `pkg update` 的错误。
- 已安装版本等于或高于候选版时，不会升级；例如正式版 `0.18.5` 高于 `0.18.5~rc1`。
- 包版本已更新而网页仍显示旧版本时，确认旧服务已经停止并重新启动。
- 手工装过相同版本号的旧包时，APT 不按文件内容自动重装；先核对版本和 SHA256，不要盲目降级。
- GitHub Pages 无法访问、证书或签名验证失败时，更新可能保留旧索引。保留错误输出排查网络或密钥，不要关闭 TLS/签名验证，也不要期望更换 Termux 默认镜像会同步这个独立源。

</details>

## Publication and limits

A successful CI run for the exact source commit triggers candidate construction and audit, then isolated signing. The signed bundle is sent through a data-only `apt-incoming` branch using a repository-scoped SSH deploy key. That generated queue branch is replaced with a lease check; application/main history is not rewritten. Reviewed bundles are retained as Release assets. Pages verifies the pinned fingerprint, bundle hash, repository signature, index hashes and package checksum before deployment. The trusted-main promotion workflow has no signing secret or cross-repository write token. It verifies the incoming signature before any write permission is used, rejects downgrades and same-version replacement, preserves the other channel, and supports idempotent recovery.

Release metadata expires after 90 days. Expired or invalid metadata must fail closed; contact the maintainer to renew it. Expired metadata retained from another channel remains rejected by clients; it cannot authorize new package content. Old release assets remain available for diagnosis and deliberate rollback. Third-party licenses are included inside each package. Go/JavaScript security scanners do not prove absence of C/C++ or unknown vulnerabilities.

No application source archive, account credentials, cookies, private books or build logs are published here. Frontend JavaScript and binary dependency metadata remain inspectable as with any distributed Web application.

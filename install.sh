#!/usr/bin/env bash
# Termux bootstrap. Packages are verified by APT against the pinned signing key.
set -euo pipefail
nr_main() (
  channel=testing no_start=0 configure=0
  if [[ -f ${PREFIX:-}/etc/apt/sources.list.d/novel-reader.list ]]; then
    channel=$(awk '/^[[:space:]]*deb / {print $(NF-1); exit}' "$PREFIX/etc/apt/sources.list.d/novel-reader.list")
  fi
  while (($#)); do
    case "$1" in
      --channel) channel=${2:?missing channel}; shift ;;
      --no-start) no_start=1 ;;
      --configure-only) configure=1 ;;
      *) printf 'Unknown option: %s\n' "$1" >&2; return 2 ;;
    esac
    shift
  done
  [[ $channel == testing || $channel == stable ]] || return 2
  nr_platform
  umask 077
  state="$HOME/.local/share/novel-reader-installer"
  [[ ! -L $state ]] || { echo '安装器目录不能是符号链接。' >&2; return 1; }
  if [[ -d $state && ! -f $state/.installer-owned ]] && [[ -n $(ls -A "$state") ]]; then
    echo '安装器目录已有未知内容，请先人工检查。' >&2; return 1
  fi
  mkdir -p "$state"; chmod 700 "$state"
  touch "$state/.installer-owned"
  log="$state/install-$(date +%Y%m%d-%H%M%S)-$$.log"
  tmp= stopped=0 installing=0 running=0
  tmp=$(mktemp -d "${TMPDIR:-$PREFIX/tmp}/novel-reader-install.XXXXXX")
  trap 'nr_cleanup "$?"' EXIT
  nr_cleanup() {
    local result=$1
    rm -rf "$tmp"
    if ((result)); then
      if ((stopped && !installing && running)); then novel-reader start >>"$log" 2>&1 || true; fi
      printf '安装未完成，原始日志：%s\n' "$log" >&2
    fi
  }
  printf '准备安装依赖…\n'
  pkg install -y curl gnupg util-linux tar coreutils >>"$log" 2>&1 </dev/null
  exec 9>"$state/install.lock"
  flock -n 9 || { echo '另一个安装器正在运行。' >&2; return 1; }
  printf '验证软件源签名公钥…\n'
  curl -fsSL --proto '=https' --proto-redir '=https' https://kalenty.github.io/novel-reader-packages/novel-reader.asc -o "$tmp/key" >>"$log" 2>&1
  nr_key "$tmp/key" >>"$log" 2>&1
  mkdir -p "$PREFIX/etc/apt/"{keyrings,sources.list.d,preferences.d}
  install -m 644 "$tmp/key" "$PREFIX/etc/apt/keyrings/novel-reader.asc.new"
  mv "$PREFIX/etc/apt/keyrings/novel-reader.asc.new" "$PREFIX/etc/apt/keyrings/novel-reader.asc"
  list="$PREFIX/etc/apt/sources.list.d/novel-reader.list"
  printf 'deb [arch=aarch64 signed-by=%s/etc/apt/keyrings/novel-reader.asc] https://kalenty.github.io/novel-reader-packages %s main\n' "$PREFIX" "$channel" > "$tmp/list"
  cat > "$tmp/pin" <<'PINS'
Package: novel-reader
Pin: origin "kalenty.github.io"
Pin-Priority: 500

Package: *
Pin: origin "kalenty.github.io"
Pin-Priority: -1
PINS
  install -m 644 "$tmp/list" "$list"
  install -m 644 "$tmp/pin" "$PREFIX/etc/apt/preferences.d/novel-reader"
  opts=(-o "Dir::Etc::sourcelist=$list" -o Dir::Etc::sourceparts=- -o APT::Get::List-Cleanup=0 -o APT::Update::Error-Mode=any)
  printf '检查可用版本…\n'
  apt-get "${opts[@]}" update >>"$log" 2>&1 </dev/null
  ((configure)) && { echo '软件源已配置。'; return 0; }
  candidate= installed=
  candidate=$(apt-cache "${opts[@]}" policy novel-reader | awk '/Candidate:/ {print $2; exit}')
  [[ -n $candidate && $candidate != '(none)' ]] || { echo '该通道没有可安装版本。' >&2; return 1; }
  installed=$(dpkg-query -W -f='${Version}' novel-reader 2>/dev/null || true)
  if [[ -n $installed ]] && dpkg --compare-versions "$installed" ge "$candidate"; then
    printf '已安装最新或更高版本：%s\n' "$installed"
  else
    printf '下载版本 %s…\n' "$candidate"
    apt-get "${opts[@]}" --download-only -y install "novel-reader=$candidate" >>"$log" 2>&1 </dev/null
    if command -v novel-reader >/dev/null; then
      if novel-reader status >>"$log" 2>&1; then running=1; fi
      if ((!running)) && curl -fsS --max-time 2 "http://127.0.0.1:${NOVEL_READER_PORT:-8080}/api/auth" >/dev/null 2>&1; then
        echo '检测到无法识别的运行实例，请手动停止后重试。' >&2; return 1
      fi
      novel-reader stop >>"$log" 2>&1
      stopped=1
    fi
    data=
    data=$(realpath -m "${NOVEL_READER_DATA:-$HOME/.local/share/novel-reader}")
    [[ $data != / && $state != "$data" && $state != "$data/"* ]] || { echo '备份目录不能位于书库中。' >&2; return 1; }
    if [[ -d $data ]]; then
      printf '备份现有数据…\n'
      nr_backup "$data" "$state" >>"$log" 2>&1
    fi
    installing=1
    printf '安装软件包…\n'
    apt-get "${opts[@]}" -y install "novel-reader=$candidate" >>"$log" 2>&1 </dev/null
  fi
  if ((!no_start)); then
    printf '启动阅读器…\n'
    novel-reader start >>"$log" 2>&1 </dev/null
  fi
  printf '完成。访问 http://127.0.0.1:%s\n日志：%s\n' "${NOVEL_READER_PORT:-8080}" "$log"
)
nr_platform() {
  [[ ${PREFIX:-} == /data/data/com.termux/files/usr ]] && command -v pkg >/dev/null && [[ $(dpkg --print-architecture) == aarch64 ]] || {
    echo '请在 aarch64 Android Termux 中运行。' >&2; return 1;
  }
}
nr_key() {
  local info
  info=$(gpg --batch --show-keys --with-colons "$1" 2>/dev/null)
  [[ $(printf '%s\n' "$info" | awk -F: '$1=="pub" {n++} END {print n+0}') == 1 && $(printf '%s\n' "$info" | awk -F: '$1=="fpr" {print $10; exit}') == 4A5257DA36C1DD201DD5725A7D02DF8EE817027D ]] || { echo '签名公钥不匹配。' >&2; return 1; }
}
nr_backup() {
  local data=$1 state=$2 snapshot
  snapshot=$(mktemp "$state/backup.XXXXXX")
  if ! tar -C "$data" -cf "$snapshot" . || ! tar -tf "$snapshot" >/dev/null; then
    rm -f "$snapshot"; return 1
  fi
  chmod 600 "$snapshot"
  [[ ! -f $state/backup.tar ]] || mv -f "$state/backup.tar" "$state/backup.previous.tar"
  mv "$snapshot" "$state/backup.tar"
}
if [[ -z ${BASH_SOURCE[0]:-} || ${BASH_SOURCE[0]} == "$0" ]]; then nr_main "$@"; fi

#!/usr/bin/env bash
# 安装固定版本的 opencode 1 到 ~/.opencode/bin。
#
# 不用官方 install 脚本：它在非 TTY 下用不带 -f 的 curl 取 release 包，CDN 返回 5xx
# 错误页时会把 HTML 当成 tar.gz 存盘，随后 `tar: not in gzip format` 让整个 job 失败。
#
# 来源只有 npm registry：GitHub release 不发布校验文件，无法按版本校验。这里用该版本
# 元数据里的 dist.integrity（sha512）校验 tarball，不匹配直接退出，不静默换源——这个
# 二进制随后会持有 GITHUB_TOKEN 跑审查 agent。
set -euo pipefail

version="${1:?usage: install_opencode.sh <version>}"
# 版本会拼进 npm 包名与元数据 URL，先拒绝不合法字符，避免路径/查询注入
case "$version" in
  *[!0-9A-Za-z.-]*)
    echo "::error::非法版本号: ${version}" >&2
    exit 1
    ;;
esac

case "$(uname -m)" in
  x86_64) arch=x64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *)
    echo "::error::unsupported arch: $(uname -m)" >&2
    exit 1
    ;;
esac
# 与官方脚本一致：x64 且无 avx2 时改用 baseline 构建
if [ "$arch" = x64 ] && ! grep -qwi avx2 /proc/cpuinfo 2>/dev/null; then
  arch=x64-baseline
fi

pkg="opencode-linux-${arch}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

if ! curl -fsSL --retry 3 --retry-delay 3 --retry-all-errors --max-time 60 \
     -o "$tmp/meta.json" "https://registry.npmjs.org/${pkg}/${version}"; then
  echo "::error::${pkg}@${version} 的 npm 元数据获取失败（版本未发布或 registry 不可用）" >&2
  exit 1
fi
tarball="$(jq -r '.dist.tarball // empty' "$tmp/meta.json")"
if [ -z "$tarball" ]; then
  echo "::error::${pkg}@${version} 元数据里没有 dist.tarball" >&2
  exit 1
fi
integrity="$(jq -r '.dist.integrity // empty' "$tmp/meta.json" | awk '{print $1}')"
case "$integrity" in
  sha512-*) ;;
  *)
    echo "::error::${pkg}@${version} 元数据里没有 sha512 dist.integrity" >&2
    exit 1
    ;;
esac

# -f：4xx/5xx 直接失败，绝不把错误页喂给 tar；--retry-all-errors 覆盖 5xx 与连接重置
curl -fL --retry 3 --retry-delay 3 --retry-all-errors --max-time 300 \
  -o "$tmp/pkg.tgz" "$tarball"

actual="sha512-$(openssl dgst -sha512 -binary "$tmp/pkg.tgz" | base64 | tr -d '\n')"
if [ "$actual" != "$integrity" ]; then
  echo "::error::${pkg}@${version} sha512 校验失败：期望 ${integrity}，实际 ${actual}" >&2
  exit 1
fi

tar -xzf "$tmp/pkg.tgz" -C "$tmp"
binary="$(find "$tmp" -type f -name opencode -print -quit)"
if [ -z "$binary" ] || [ ! -x "$binary" ]; then
  echo "::error::${pkg}@${version} 里没有可执行的 opencode" >&2
  exit 1
fi

mkdir -p "$HOME/.opencode/bin"
install -m 755 "$binary" "$HOME/.opencode/bin/opencode"
"$HOME/.opencode/bin/opencode" --version

#!/usr/bin/env bash
# hfw publish FILE --tag TAG [--name ASSET] [--title T] [--notes N] [--repo OWNER/REPO] [--yes]
# Store a finished video as a GitHub release asset (videos are never committed). Without --yes it is a dry run that
# prints what would happen. With --yes: creates the release TAG as a pre-release if it does not exist (so it never
# becomes "Latest"; the tag points at the default branch), uploads FILE as ASSET (default: its basename), replacing an
# asset of that name, and writes FILE.published.json (repo, tag, asset, url, sha256, size, time).
# Publishing is outward-facing: run it with --yes only when the user asked for this upload.
# Works for any video (narrated-explainer chapters too).
set -euo pipefail
file="${1:-}"; [ -n "$file" ] && [ -f "$file" ] || { echo "usage: hfw publish FILE --tag TAG [--name ASSET] [--title T] [--notes N] [--repo R] [--yes]" >&2; exit 2; }
shift
tag=""; name="$(basename "$file")"; title=""; notes=""; repo=""; yes=0
while [ $# -gt 0 ]; do
  case "$1" in
    --tag) tag="$2"; shift 2 ;; --name) name="$2"; shift 2 ;; --title) title="$2"; shift 2 ;;
    --notes) notes="$2"; shift 2 ;; --repo) repo="$2"; shift 2 ;; --yes) yes=1; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
[ -n "$tag" ] || { echo "--tag is required (e.g. videos)" >&2; exit 2; }
[[ "$tag" =~ ^[A-Za-z0-9._/-]+$ ]] || { echo "bad tag: $tag" >&2; exit 2; }
[[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "bad asset name (letters, digits, . _ - only): $name" >&2; exit 2; }
[ -n "$repo" ] || repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
size=$(stat -c %s "$file")
[ "$size" -lt 2147483648 ] || { echo "$file is over GitHub's 2 GiB asset limit" >&2; exit 1; }
sha=$(sha256sum "$file" | cut -d' ' -f1)
info="$(gh repo view "$repo" --json visibility,defaultBranchRef -q '.visibility + " " + .defaultBranchRef.name')"
visibility="${info% *}"; branch="${info#* }"
if gh release view "$tag" --repo "$repo" --json tagName >/dev/null 2>&1; then
  exists=1
  replaces=$(gh release view "$tag" --repo "$repo" --json assets -q ".assets[] | select(.name == \"$name\") | .name" || true)
else
  exists=0; replaces=""
fi
echo "repo:     $repo ($visibility)"
echo "release:  $tag $([ $exists = 1 ] && echo '(exists)' || echo "(will be created as a pre-release on $branch)")"
echo "asset:    $name ($(numfmt --to=iec "$size"), sha256 $sha)$([ -n "$replaces" ] && echo ' REPLACES the existing asset of that name')"
if [ "$yes" != 1 ]; then echo "dry run: add --yes to publish"; exit 0; fi

if [ $exists = 0 ]; then
  gh release create "$tag" --repo "$repo" --prerelease --target "$branch" \
    --title "${title:-$tag}" --notes "${notes:-Walkthrough videos. Assets are uploaded with hfw publish; the sha256 of each is in the uploader's FILE.published.json.}"
fi
tmpdir="$(mktemp -d)"; trap 'rm -rf "$tmpdir"' EXIT
ln -s "$(realpath "$file")" "$tmpdir/$name"
gh release upload "$tag" "$tmpdir/$name" --repo "$repo" --clobber
url=$(gh release view "$tag" --repo "$repo" --json assets -q ".assets[] | select(.name == \"$name\") | .url")
python3 - "$file.published.json" "$repo" "$tag" "$name" "$url" "$sha" "$size" <<'EOF'
import json, sys, datetime
p, repo, tag, name, url, sha, size = sys.argv[1:]
json.dump({"repo": repo, "tag": tag, "asset": name, "url": url, "sha256": sha, "size": int(size),
           "published": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")},
          open(p, "w"), indent=1)
EOF
echo "published: $url"
echo "record:    $file.published.json"

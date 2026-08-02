---
name: imgslim
description: Compress and convert image assets in software projects with iLoveIMG-class perceptual quality search (DSSIM-driven, MozJPEG/pngquant/libwebp). Placement-aware — flags images that are larger than their location allows (Android density buckets, iOS asset catalogs, favicons) and resizes before compressing. Format-aware — only converts PNG→WebP when the target platform actually supports it. Use when the user asks to compress/optimize/shrink images, 压缩图片, convert to webp, audit image assets, or when app icons or assets look oversized.
---

# imgslim — project-aware image compression

You are compressing **assets inside a software project**, not just files. Three
judgments come before any encoding, in this order: **right size → right format
→ maximum compression**. The script does the mechanical work; you do the
project-context judgment.

Engine: `scripts/imgslim.py` (relative to this skill's directory; python3, no
Python deps). First run per machine: `imgslim.py deps` — if tools are missing,
offer to `brew install pngquant oxipng webp mozjpeg dssim`.

## Workflow

### 1. Inventory & size audit

```
python3 <skill_dir>/scripts/imgslim.py analyze <paths> [--json]
```

Lists every image (largest first) with dimensions and **OVERSIZED flags** where
the placement dictates an expected size (Android `mipmap-<density>` launcher
icons, iOS asset-catalog `Contents.json` entries, `NxN` filenames,
apple-touch-icon, OG images). A 1024×1024 PNG in `mipmap-mdpi/ic_launcher.png`
is flagged: expected 48×48.

The script only knows path-based rules. For unflagged suspicious images, apply
judgment: read where the image is used (layout files, CSS, `<img>` tags,
`Image()` calls). A 3000px photo rendered in a 400px card should be resized to
~2× its display size (800px). When in doubt about intended display size, ask —
don't guess destructive downscales.

### 2. Format decision — read references/format-compat.md

Default: **keep the current format.** Convert only when the project context
proves it's safe. Check before proposing PNG→WebP:

- **Android**: `minSdk` in `build.gradle(.kts)` — WebP lossy needs API 14+,
  lossless/alpha needs API 18+. Launcher icons in `mipmap-*` must stay PNG
  (some launchers mishandle WebP). Android Studio's own converter enforces the
  same rules.
- **iOS**: native WebP decode needs iOS 14+ (check deployment target). App
  Icon asset catalogs must stay PNG.
- **Web**: WebP is safe for all evergreen browsers + Safari 14+. Check
  `browserslist` / target audience. Files referenced from README/docs rendered
  on GitHub: WebP renders fine on github.com, but keep PNG if the docs are
  also consumed elsewhere (crates.io, npm README renderers vary).
- **Anything with transparency going to JPEG**: refuse; JPEG has no alpha.

Photographic content → prefer lossy (WebP/JPEG). Flat-color UI art/icons →
PNG (or lossless WebP); the script tries both for WebP and keeps the smaller.

### 3. Compress

```
python3 <skill_dir>/scripts/imgslim.py compress <files...> \
    --preset balanced --format keep --in-place
```

- Presets: `high` (visually lossless, DSSIM ≤ 0.0010) / `balanced` (default,
  ≤ 0.0028) / `small` (≤ 0.0065) / `lossless`. Lossy presets binary-search the
  quality per image against the DSSIM target — never hand-pick fixed qualities.
  Benchmarked (docs/BENCHMARK.md): `high` matches TinyPNG/iLoveIMG's default
  quality at a 6–9% smaller file for JPEG; `balanced` is deliberately more
  aggressive than those services. If the user says "compress like
  TinyPNG/iLoveIMG would", use `high`.
- Fixing an OVERSIZED flag: add `--resize WxH` (exact, for icons) or
  `--max-dim N` (bounding box, for photos).
- `--in-place` only when the file is tracked and clean in git (check
  `git status` first) so the change is revertible. Otherwise omit it (writes
  `name.min.ext` alongside) or use `--output-dir`.
- **Conversion never deletes the source.** After `--format webp`, the new
  `.webp` sits next to the original: update every code/markup reference to the
  old filename (grep for the basename), verify builds still pass, then delete
  the originals yourself.
- The script guarantees results are never larger than the original
  (same-format; status `kept` means it was already optimal).

### 4. Report

Show the user the per-file table the script prints (or summarize `--json` for
large batches): original → new size, %, resizes and conversions performed,
plus reference updates you made. Recommend they visually spot-check one or two
of the most aggressively compressed files (`small` preset especially).

## Safety rules

- Never compress in `node_modules`, build outputs, vendored dirs (analyze
  already skips them) or third-party assets with license-required integrity.
- Never `--in-place` on files with uncommitted changes.
- Never downscale below a size you inferred — only below a size the placement
  *declares* (flags, Contents.json, explicit user intent).
- Batch >50 files: show the analyze summary and get confirmation before
  compressing.

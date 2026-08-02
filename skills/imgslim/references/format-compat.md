# Format compatibility reference

Decision inputs for the "should I convert this?" judgment. Verify against the
project's actual config files — never assume.

## WebP support matrix

| Platform | Lossy WebP | Lossless / alpha | Animated | Where to check |
|---|---|---|---|---|
| Android | API 14+ | API 18+ | API 28+ (via ImageDecoder) | `minSdk` in `build.gradle(.kts)` / `flavor` overrides |
| iOS / macOS native (UIImage/NSImage/SwiftUI) | iOS 14+ / macOS 11+ | same | ❌ (needs SDWebImage etc.) | deployment target in project settings |
| Browsers | all evergreen, Safari 14+ | same | same | `browserslist`, analytics, target audience |
| React Native | 0.60+ Android; iOS needs opt-in pods | varies | ❌ default | package.json + Podfile |
| Flutter | ✅ all | ✅ | ✅ | — |
| GitHub README rendering | ✅ | ✅ | ✅ | but check other renderers (npm, crates.io, PyPI) if the same README ships there |
| Electron / Tauri (webview) | ✅ | ✅ | ✅ | — |

## Hard "keep PNG" cases

- Android launcher icons (`mipmap-*/ic_launcher*.png`) — adaptive-icon XML may
  reference them; some OEM launchers mishandle WebP. Android Studio's builtin
  converter refuses these too.
- iOS AppIcon asset catalogs — App Store validation expects PNG.
- Notification icons on Android (`ic_stat_*`) — must be PNG (and flat white+alpha).
- favicon `.ico` pipelines — leave `.ico` alone; a sibling `favicon-32x32.png` can be optimized in place but not converted.
- Sprite sheets consumed by engines that hard-require PNG (check the loader).
- Any file whose *bytes* are checksummed/signed (integrity manifests).

## Format choice by content type

| Content | Best format (compat permitting) | Notes |
|---|---|---|
| Photo, screenshot with gradients | WebP lossy > JPEG (mozjpeg) | ~25–35% smaller than JPEG at equal DSSIM |
| Flat UI art, logos, icons | PNG (pngquant) or WebP lossless | script tries both WebP modes, keeps smaller |
| Needs transparency + photo content | WebP lossy (with alpha) | PNG will be huge; JPEG impossible |
| Tiny icons < 10 KB | keep PNG | conversion savings don't justify reference churn |

## Android density expectations (dp × factor = px)

| Bucket | factor | launcher (48dp) | adaptive fg (108dp) | notification (24dp) |
|---|---|---|---|---|
| mdpi | 1.0 | 48 | 108 | 24 |
| hdpi | 1.5 | 72 | 162 | 36 |
| xhdpi | 2.0 | 96 | 216 | 48 |
| xxhdpi | 3.0 | 144 | 324 | 72 |
| xxxhdpi | 4.0 | 192 | 432 | 96 |

Generic `drawable-*` images have no fixed rule — infer from layout usage
(`layout_width`/`dp` values × factor) before resizing.

## Web asset expectations

| Asset | Size |
|---|---|
| favicon-16x16 / 32x32 / 48x48 | as named |
| apple-touch-icon | 180×180 |
| OG / Twitter card image | 1200×630 (max useful) |
| `srcset` responsive images | each candidate ≈ its descriptor; largest ≈ 2× max display width |

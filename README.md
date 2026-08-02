# imgslim

**Project-aware image compression as an agent skill** — for Claude Code and Codex.

Not another "run pngquant on everything" wrapper. imgslim treats images as *assets inside a software project* and makes three judgments in order:

1. **Right size first** — flags images bigger than their placement allows: a 1024×1024 PNG in `mipmap-mdpi/ic_launcher.png` should be 48×48; iOS asset-catalog sizes come straight from `Contents.json`. Resize, *then* compress.
2. **Right format** — converts PNG→WebP only when the project proves it's safe (Android `minSdk` ≥ 18, iOS 14+, browserslist…). Launcher icons, App Store icons, notification icons stay PNG. Not everything should be WebP — and the agent checks, you don't have to.
3. **iLoveIMG-class compression** — per-image perceptual quality search: binary-search the encoder quality against a DSSIM target (MozJPEG / pngquant / libwebp underneath), so every image gets the lowest quality that's still visually clean, instead of one fixed setting for all. 100% local, nothing uploaded.

> 面向软件项目的图片压缩 skill:先按位置判断该有的尺寸(Android 密度桶 / iOS Contents.json),再按项目兼容性决定格式(不无脑转 WebP),最后用感知质量搜索压到 iLoveIMG 的水平。全本地。

## Install

```bash
git clone https://github.com/zjywill/imgslim && cd imgslim && ./install.sh
```

The installer brew-installs codec deps (`pngquant oxipng webp mozjpeg dssim`) and symlinks the skill into both `~/.claude/skills/` and `~/.codex/skills/`.

Cross-platform: the engine is stdlib-only python3 and works on Linux/Windows too — decode/resize uses `sips` on macOS and falls back to ImageMagick elsewhere; `imgslim.py deps` prints the right install command per platform (apt/cargo on Linux, scoop on Windows).

Claude Code plugin route instead of the symlink:

```
/plugin marketplace add zjywill/imgslim
/plugin install imgslim@imgslim
```

## Use

Just ask your agent, in any project:

- *"compress the images in this repo"*
- *"把 assets 里的图压一下,能转 webp 的转 webp"*
- *"audit the app icons, some look oversized"*

Or drive the engine directly:

```bash
python3 skills/imgslim/scripts/imgslim.py analyze .
python3 skills/imgslim/scripts/imgslim.py compress assets/*.png --preset balanced --in-place
python3 skills/imgslim/scripts/imgslim.py compress photo.jpg --format webp --preset high
```

Presets: `high` (visually lossless) · `balanced` · `small` · `lossless`. Results are never larger than the original.

## Layout

```
skills/imgslim/SKILL.md              agent workflow + judgment rules
skills/imgslim/references/           WebP compat matrix, platform size tables
skills/imgslim/scripts/imgslim.py    engine: analyze / compress / deps (python3, stdlib only)
.claude-plugin/                      Claude Code plugin + marketplace manifests
install.sh                           deps + symlinks for Claude Code and Codex
```

## License

MIT

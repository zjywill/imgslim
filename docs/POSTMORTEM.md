# Postmortem: visible banding on dark UI assets (2026-08-02)

An agent ran imgslim 0.1.0 over an Android app's `res/` tree (267 images,
`--in-place`, then-default `balanced` preset). The user spotted visible
blotching on a dark flat-color icon background in the PR diff.

## What went wrong

1. **Lossy-on-lossy webp.** The res tree's webp files were already lossy
   (optimized at export). Re-encoding stacked a second generation of loss.
   Measured DSSIM vs the committed original was only 0.0008 — numerically
   "visually lossless" — yet banding on the flat dark background was obvious
   at a glance. SSIM-family metrics under-weight banding in large smooth
   regions; flat dark gradients are the worst case.
2. **Default too aggressive.** `balanced` (DSSIM ≤ 0.0028) is tuned for
   photos, not UI chrome.
3. **No human verification step.** The damage shipped into a PR before anyone
   looked at an image.

PNG results from the same batch were fine (pngquant on flat icons measured
DSSIM ≈ 0.00001–0.0002) — the damage was specific to lossy webp re-encoding.

## What changed (0.2.0)

- Same-format lossy re-encode of already-lossy webp is **refused** by default
  (`--force` to override; RIFF chunks are walked so VP8X containers are
  detected too).
- Default preset is `high` (DSSIM ≤ 0.0010, matches TinyPNG/iLoveIMG default
  quality per BENCHMARK.md); SKILL.md pins icons/logos/UI art to
  high-or-lossless.
- PNG output goes through the same DSSIM gate as other codecs (escalate
  quality, then fall back to lossless).
- `--report review.html` renders every changed file before/after;
  SKILL.md makes human review mandatory for lossy batches and forbids
  agents from committing image changes.

## Rules of thumb encoded

- Compressed-once is the ceiling for lossy assets; shrinking further means
  re-exporting from the design source, not re-encoding.
- Trust the metric to find the knee, not to declare victory — a human looks
  at dark flat areas before anything is committed.

# Benchmark vs TinyPNG & iLoveIMG

2026-08-02, same source files uploaded to each service's web UI (default settings),
DSSIM measured against the pristine originals (lower = closer to original; 0 = identical).

## photo.jpg — 1600×900 photographic JPEG, 222.3 KB

| | size | savings | DSSIM |
|---|---|---|---|
| TinyPNG | 62.8 KB | −71.8% | 0.00112 |
| iLoveIMG | 61.0 KB | −72.6% | 0.00084 |
| **imgslim `high`** | **57.3 KB** | **−74.2%** | **0.00085** |
| imgslim `balanced` | 35.8 KB | −83.9% | 0.00267 |

At identical quality (DSSIM 0.00085 vs iLoveIMG's 0.00084), imgslim `high` is
**6% smaller than iLoveIMG and 9% smaller than TinyPNG**. `balanced` trades more
quality for a 42% smaller file than either service produces.

## hero.png — 1600×900 screenshot PNG, 1.5 MB

| | size | savings | DSSIM |
|---|---|---|---|
| TinyPNG | 347.3 KB | −76.9% | 0.00092 |
| iLoveIMG | 345.5 KB | −77.0% | 0.00124 |
| imgslim `balanced` | 377.3 KB | −74.9% | **0.00065** |
| imgslim `small` | 307.8 KB | −79.5% | 0.00159 |

Same quality-size tradeoff curve (all three use pngquant-class quantization):
`balanced` beats both on quality at ~9% larger, `small` beats both on size at
slightly lower quality. The services' default operating point sits between the
two presets.

## logo.png — 400×400 flat-color PNG, 625.5 KB

| | size | DSSIM |
|---|---|---|
| TinyPNG | 206 B | 0.0 |
| iLoveIMG | 204 B | 0.0 |
| imgslim | 205 B | 0.0 |

Dead tie — palette quantization fully solves this case for everyone.

## Takeaways

- JPEG: imgslim's DSSIM-targeted search beats both services at equal quality
  (mozjpeg + per-image search vs their fixed-recipe encoders).
- PNG: parity, as expected — everyone is running pngquant-style quantization.
- `high` ≈ the services' default quality level; `balanced` is deliberately more
  aggressive; use `high` when you want "what TinyPNG would have done, slightly smaller".
- Plus the two things the services can't do: local-only processing, and
  placement-aware sizing/format conversion in the same pass.

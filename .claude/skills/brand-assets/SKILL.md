---
name: brand-assets
description: Create and export project logo/banner SVG assets to light/dark PNG variants. Covers the full lifecycle from initial design exploration through SVG creation to themed PNG export. Use when creating logos, banners, or regenerating PNG exports from SVG source files.
model: opus
argument-hint: '[path/to/assets or SVG file]'
---

# Project Logo and Banner Assets

Create, maintain, and export project logo and banner assets as SVGs with light/dark PNG variants.

## Asset variants

Every project produces four SVG variants, each with light and dark PNG exports:

1. **Favicon** (`favicon.svg`): The project icon only, no text, no margins. Tight-cropped to the icon's bounding box. Used as `html_favicon` in Sphinx and as the browser tab icon. Transparent background. Does not need PNG exports (browsers handle SVG favicons natively).

2. **Square logo** (`logo-square.svg`): The project icon with the project name centered below it. Used as the Sphinx sidebar logo (`html_logo`). Transparent background. The viewBox is taller than the icon to accommodate the text below.

3. **Banner** (`logo-banner.svg`): Horizontal layout with the icon on the left, project name and tagline to the right. Transparent background. Used in the GitHub readme.

4. **Social banner** (`banner-{style}.svg`): Same layout as the banner but with a decorative opaque background (e.g., marble veins, gradients, wave patterns). Used for OpenGraph/social previews. Opaque background.

Each SVG produces two PNGs: `{name}-light.png` and `{name}-dark.png`. The favicon is SVG-only (no PNG exports needed).

## Design exploration

When creating assets for a new project, start with a broad exploration phase to find a visual direction before refining.

### Phase 1: Generate candidates

Prompt pattern:

> Create several PNG versions of \{base-svg} but with different abstract backgrounds (curvy, bitmap, slopes, splines, gradients, noise, halftone, topographic, marble, waves, geometric, etc). Generate 30 of them, all singularly different, so I can choose a direction. Place them in \{assets-dir}.

Use `rsvg-convert` or a Python script (Pillow) to composite the base SVG over programmatically generated backgrounds. Number each output `banner-{nn}-{descriptor}.png` (e.g., `banner-12-wind-lines.png`, `banner-27-marble-veins.png`).

### Phase 2: Pick a direction

The user reviews the candidates and picks one or more to refine. Delete the rest.

### Phase 3: Refine to SVG

Recreate the chosen design as a clean, hand-authored SVG:

- Use CSS classes for all themed colors (no inline `style` attributes).
- Keep the SVG source in light-mode only (no `@media` queries).
- Trace decorative elements from the raster reference if needed (see "Reverse-engineering raster to SVG" below).

## Naming conventions

- `{name}.svg` is the canonical source (always renders in light mode).
- `{name}-light.png` is the light-theme PNG export.
- `{name}-dark.png` is the dark-theme PNG export.

## Color themes

SVGs use CSS classes for themed properties (fills, strokes). To export a themed PNG:

1. Read the SVG and identify all CSS classes and their light-mode values.
2. Build a replacement `<style>` block with dark-mode colors swapped in.
3. Write a temporary SVG with the baked style.
4. Convert to PNG with `rsvg-convert`.
5. Delete the temporary SVG.

Typical light/dark color pairs (Tailwind Slate palette):

| Role       | Light     | Dark      |
| ---------- | --------- | --------- |
| Frame/ring | `#334155` | `#94A3B8` |
| Handle out | `#334155` | `#94A3B8` |
| Handle in  | `#475569` | `#CBD5E1` |
| Title text | `#1E293B` | `#F1F5F9` |
| Tagline    | `#64748B` | `#CBD5E1` |
| Background | `#F8FAFC` | `#0F172A` |
| Vein light | `#e2e8ef` | `#1a2535` |
| Vein dark  | `#c6cfda` | `#253040` |

## Backgrounds

- **Transparent background** (default for logo-square and logo-banner): Do not add a `<rect>` background. The PNG will have alpha transparency, suitable for overlaying on any surface.
- **Opaque background** (for social banners): The SVG has a background `<rect>` with a `.bg` class. Swap its fill color for the target theme. Both light and dark PNGs get their respective solid background.

## Conversion tool

Use `rsvg-convert` (from librsvg):

```
rsvg-convert -o output.png input.svg
```

If `rsvg-convert` is unavailable, fall back to `inkscape --export-type=png --export-filename=output.png input.svg`.

## Export workflow

1. **Discover SVGs.** If `$ARGUMENTS` is a directory, find all `.svg` files in it. If it's a specific file, use that. Default to `docs/assets/`.

2. **For each SVG**, read it and identify:

   - All CSS classes and their current (light-mode) values.
   - Whether a background `<rect>` with `.bg` class exists (opaque) or not (transparent).

3. **Generate light PNG.** The SVG already has light-mode styles, so convert directly:

   - If transparent: `rsvg-convert -o {name}-light.png {name}.svg`
   - If opaque: convert as-is (the `.bg` rect has the light fill).

4. **Generate dark PNG.** Create a temporary SVG with dark-mode colors:

   - Replace the `<style>` block with dark-mode values.
   - If opaque, the `.bg` fill is swapped to the dark background color.
   - Convert the temp SVG, then delete it.

5. **Report** the generated files and their sizes.

## Rules

- Never modify the source `.svg` files. Only create temporary copies for baking.
- Always clean up temporary SVGs after conversion.
- SVG source files must NOT contain `@media (prefers-color-scheme: dark)` blocks. Light-mode styles are the only styles in the SVG. Dark mode is handled exclusively through baked PNG exports.
- The font stack for text elements is: `'Inter', 'Segoe UI', system-ui, -apple-system, 'Helvetica Neue', Arial, sans-serif`.
- When creating new SVGs, use the Tailwind Slate palette for all grays and the same `radialGradient` for the lens glass.

## Sphinx integration

### `docs/conf.py`

Wire the assets into the Furo theme:

```python
html_logo = "assets/logo-square.svg"
html_favicon = "assets/favicon.svg"
html_theme_options = {
    "sidebar_hide_name": True,
    # ...
}
```

- `html_logo`: Points to the square logo (with project name baked in). Combined with `"sidebar_hide_name": True` to avoid a duplicate auto-generated name below the SVG.
- `html_favicon`: Points to the icon-only favicon (no text, tight crop).

### Hiding the readme banner in Sphinx

The readme includes a centered banner image (`logo-banner.svg`) for GitHub. When the readme is included in the Sphinx front page via `{include}`, the banner is redundant with the sidebar logo. Hide it with custom CSS:

`docs/_static/custom.css`:

```css
/* Hide the readme banner on the Sphinx front page (logo already in sidebar). */
article p[align="center"]:has(img[alt="Project Name"]) {
    display: none;
}
```

Wire it in `conf.py`:

```python
html_static_path = ["_static"]
html_css_files = ["custom.css"]
```

Replace `"Project Name"` with the actual `alt` text of the banner `<img>` in the readme.

## Reverse-engineering raster to SVG

When a design exists only as a raster image (PNG/JPEG) and needs to be reproduced as a clean SVG, use pixel analysis to extract geometry and colors.

### General approach

1. **Identify the background color.** Sample pixels in a known empty region. This establishes the threshold for separating foreground elements from background.

2. **Scan for foreground features.** Using Pillow + NumPy, iterate over the image in slices (vertical columns for horizontal features, horizontal rows for vertical features). At each slice, threshold grayscale values to find pixels that differ from the background.

3. **Cluster pixels into distinct elements.** Group adjacent foreground pixels within a slice. A gap larger than 3-5px indicates a separate element. For each cluster, record:

   - Center position (x, y)
   - Thickness (extent of the cluster)
   - Color (sample the middle pixel's RGB)

4. **Trace paths across slices.** Match clusters across adjacent slices by proximity to build continuous paths. Each path becomes a series of (x, y) sample points.

5. **Fit SVG paths.** Convert the sampled points into SVG cubic bezier curves:

   - Use `C` (cubic bezier) for the initial segment.
   - Use `S` (smooth cubic bezier) for continuations. Each `S` needs 4 coordinates (control point + endpoint); fewer causes the path to terminate early.
   - Extend paths past the viewBox edges (e.g., `x=-20` and `x=1300` for a 1280-wide image) so lines reach the borders cleanly.

6. **Assign colors.** Group paths by sampled RGB values. Create CSS classes for each distinct color and assign them to the corresponding paths.

### Practical tips

- **Avoid interference zones.** Skip regions occupied by text or logos when scanning. Sample from clear areas (edges, corners) and interpolate through occluded zones.
- **Loosen thresholds iteratively.** Start with a tight threshold (e.g., grayscale < 225) to find the most prominent features, then widen (< 234) to catch subtler ones.
- **Validate element counts.** Check that the same number of elements appear at multiple x positions. Inconsistencies indicate threshold issues or interference from other content.
- **Check for uniform color.** In many designs, decorative elements share one or two colors. Confirm by sampling at multiple positions before creating unnecessary CSS classes.
- **Anti-aliasing.** Raster lines have soft edges. Measure thickness from the full cluster extent (including semi-transparent edge pixels), but sample color from the cluster center where the pixel is fully opaque.

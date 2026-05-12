# ShadowDance — Feature Checklist

Use this as a QA checklist. Each section maps to a testable area of the app.

---

## Window & App

- [ ] App opens a fresh blank window on launch (no auto-restore)
- [ ] New Window (Ctrl+N) opens a second independent window, cascaded ~30px offset
- [x] Multiple windows run simultaneously with independent state
- [ ] Closing last window quits the app
- [x] Window title shows `ShadowDance` (no slideshow), `ShadowDance — name` (slideshow open), `ShadowDance — name *` (unsaved changes)

---

## File Browser (left panel, Ctrl+B to toggle)

- [ ] Directory tree navigates the full filesystem
- [ ] File list filters to supported image formats only
- [ ] Single-click a file → previews it in the viewer
- [ ] Double-click a file → toggles it in/out of the selection
- [ ] Selected files show green tint + ✓ badge in the file list
- [ ] Counter at bottom reads "X selected"
- [ ] Navigating to a new directory clears the file list display cleanly (no leftover rows from previous directory)
- [ ] Browse Directory… (Ctrl+D) opens a folder picker and navigates to it
- [ ] **Show Hidden Files** (View menu, Ctrl+H, checkable) — toggles dotfiles/hidden dirs in tree and file list; off by default

---

## Selected Files Pane (right panel, Ctrl+E to toggle)

- [ ] Pane is hidden on startup; auto-shows when first file is selected
- [ ] Toggle via View → Selected Files (Ctrl+E) or dock close button
- [ ] **Name view** — shows filenames, one per row
- [ ] **Details view** — shows filename + file size + modified date
- [ ] **Thumbnails view** — shows image grid; thumbnails load asynchronously without blocking the UI
- [ ] Thumbnail cache: switching away and back to Thumbnails view is instant
- [ ] Drag/drop reordering works in all three view modes
- [ ] Reordering in the pane immediately changes slideshow playback order
- [ ] Double-click a file in the pane → jumps to that image in the viewer
- [ ] Right-click → "Remove from selection" removes that file only
- [ ] "Clear All" button clears entire selection
- [ ] File count at bottom stays accurate after add/remove/clear
- [ ] Selecting files from a second directory adds them to the existing selection (cross-filesystem)

---

## Image Display

- [ ] Image fills the viewer area, centered on dark background
- [ ] **Fit to Window** (Ctrl+F, checkable) — image scales to fit, maintains aspect ratio
- [ ] Fit mode reacts correctly when window is resized
- [ ] EXIF orientation is applied correctly (portrait JPEGs not displayed sideways)
- [ ] **Supported formats load correctly:**
  - [ ] JPEG / JPG
  - [ ] PNG
  - [ ] WebP
  - [ ] BMP / GIF
  - [ ] TIFF
  - [ ] HEIC / HEIF (requires pillow-heif)
  - [ ] RAW: CR2, CR3, NEF, ARW, DNG, ORF (requires rawpy)
- [ ] Status bar shows filename and position (`name.jpg  [3/12]`)

---

## Navigation

- [ ] Toolbar: First ⏮ / Previous ⏪ / Play ▶ / Next ⏩ / Last ⏭ buttons render with platform icons
- [ ] Left/Right arrow keys navigate previous/next
- [ ] First/Last buttons jump to ends of the list
- [ ] Navigation wraps when loop is on; stops at end when loop is off

---

## Slideshow

- [ ] Play/Pause (Space bar) starts and stops the timer
- [ ] Toolbar play button icon changes between ▶ Play and ⏸ Pause
- [ ] Slideshow menu "Play" / "Pause" text updates to match state
- [ ] **Slide Duration…** dialog sets the per-slide interval (200ms–300,000ms)
- [ ] **Loop** (checkable menu item) — wraps around at end when on; stops at end when off
- [ ] **Shuffle** (checkable menu item) — picks a random different image each tick
- [ ] When files are selected, slideshow plays through selected files only
- [ ] When no files are selected, slideshow plays through current directory
- [ ] Changing directories while no files are selected switches slideshow to new directory
- [ ] Slideshow respects drag/drop order set in the Selection Pane
- [ ] Loop and Shuffle states are saved and restored with slideshow files

---

## Image Editing (non-destructive by default)

- [ ] Rotate Clockwise (Ctrl+R) — saves as `name_edit.ext` next to original
- [ ] Rotate Counter-Clockwise (Ctrl+Shift+R)
- [ ] Flip Horizontal
- [ ] Flip Vertical
- [ ] Crop… (Ctrl+Shift+C) — dialog shows image dimensions; accepts pixel-precise bounds
- [ ] Crop with "Overwrite original" checked — saves in place; backs up original to `.orig`
- [ ] Crop with overwrite unchecked — saves as `name_edit.ext`
- [ ] Edited file is immediately displayed in the viewer after saving

---

## Slideshow Files (.sdshow)

- [ ] **New Slideshow** — clears selection and file list; prompts to save if unsaved changes exist
- [ ] **Open Slideshow…** (Ctrl+O) — file dialog filters to `.sdshow`; restores file list, selection, playback settings, Loop/Shuffle state
- [ ] **Save Slideshow** (Ctrl+S) — saves to current path; prompts for path if unsaved
- [ ] **Save Slideshow As…** (Ctrl+Shift+S) — always prompts for a new path
- [ ] Closing window with unsaved changes → Save / Discard / Cancel prompt
- [ ] Opening another slideshow with unsaved changes → same prompt
- [ ] Saved file contains: ordered file list, current index, interval, loop, shuffle, browser directory
- [ ] Loading a slideshow restores selection indicators in the file browser

---

## Fullscreen

- [x] F11 toggles fullscreen; Escape exits fullscreen
- [x] View → Full Screen checkable item stays in sync with actual window state
- [ ] Slideshow continues playing in fullscreen

---

## Platform / Cross-platform Foundations

- [ ] Session data writes to platform-correct directory (Linux: `~/.local/share/shadowdance/`, macOS: `~/Library/Application Support/shadowdance/`, Windows: `%APPDATA%\shadowdance\`)
- [ ] No hardcoded paths inside the project directory
- [ ] `.gitignore` excludes `.venv/`, `__pycache__/`, `*.sdshow`, session data

---

## Planned Features

- [ ] **Animated GIF playback** — display animated GIFs as animations rather than a still first frame
- [ ] **Thumbnail size control** — small / medium / large toggle in the Selected Files pane toolbar
- [ ] **Recent slideshows list** — File menu submenu listing the last N opened `.sdshow` files for quick reopening
- [ ] **Keyboard shortcut reference** — Help menu item or Ctrl+? dialog listing all shortcuts
- [ ] **Thumbnail drag/drop** — intermittent wrong-position placement bug; needs a reproducible sequence to diagnose (known FIXME)

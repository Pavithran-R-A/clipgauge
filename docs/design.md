# ClipGauge design guide

ClipGauge is a desktop video tool for turning long recordings into vertical clips. The interface should feel calm and useful before it feels clever: a creator should know what to do next without learning the pipeline vocabulary.

## Palette

ClipGauge uses deep ocean and graphite surfaces with a restrained teal action color and clear blue information signals. Coral is reserved for warnings and errors; green indicates a confirmed ready state. The product palette does not use purple, violet, magenta, yellow, gold, or amber.

| Token | Value | Use |
|---|---|---|
| `--bg-canvas` | `#071215` | App canvas |
| `--bg-sidebar` | `#0A181C` | Navigation shell |
| `--surface-1` | `#102126` | Cards and panels |
| `--surface-2` | `#152A30` | Raised controls |
| `--surface-3` | `#1A333A` | Selected/hovered surfaces |
| `--border-subtle` | `#244047` | Quiet separation |
| `--border-strong` | `#31535A` | Focus and active boundaries |
| `--text` | `#F3F8F7` | Primary text |
| `--text-muted` | `#B2C2C2` | Secondary text |
| `--text-faint` | `#819597` | Tertiary text |
| `--teal` | `#18C8B5` | Primary action and selection |
| `--blue` | `#58B7FF` | Links, progress, analytics |
| `--green` | `#35C98A` | Ready and completed |
| `--coral` | `#FF7A59` | Warning and attention |
| `--error` | `#EF5D6C` | Errors |

Color is never the only state signal. Status chips also contain text, and progress bars have accessible labels and values.

## Typography

Normal product copy uses the bundled Public Sans face. Archivo Black is reserved for a small number of display headings where it improves hierarchy. Martian Mono is used only for model IDs, endpoints, hashes, versions, diagnostic IDs, and byte-level technical metadata. Human labels such as **Create clips**, **Setup & Storage**, and **AI Providers** use proportional text.

Primary body text is 14–16px with a line height of at least 1.45. Secondary text is never smaller than 13px in normal product surfaces. Uppercase is limited to compact status tags and is not used as the main navigation voice.

## Spacing, radii, and surfaces

The base spacing scale is 4, 8, 12, 16, 20, 24, 32, 40, 48, and 64px. New layout code should use these values or a documented optical adjustment. Cards use 14px radii; controls use 10px; the shell uses no decorative bevels. Borders are quiet, and elevation comes from small surface changes rather than large glows.

## Motion

Controls transition in 140–180ms. Panels and drawers transition in 200–260ms. Use opacity and transform for entry/exit, and keep progress changes interruptible. There is no permanent animated grain, particle layer, mesh gradient, or decorative background motion. Under `prefers-reduced-motion: reduce`, nonessential transitions are removed while state remains clear through color, text, and layout.

## Navigation and disclosure

The persistent navigation is organized by what people are trying to do:

| Section | Purpose |
|---|---|
| Create | Add a video and make clips |
| Sessions | Reopen previous work |
| Setup & Storage | Install, repair, and understand local components |
| AI Providers | Choose and connect scoring services |
| Integrations | Manage Pexels and Instagram |
| Privacy | See what stays local and what leaves the computer |
| Help & Diagnostics | Create a redacted support bundle |
| About | Version, license, attribution, and notices |

Simple mode explains choices in plain language. Advanced disclosure is available from the relevant screen and may show provider IDs, endpoints, revisions, hashes, and structured-output details. Technical details never replace the normal summary.

## Icons

Use the bundled ClipGauge mark and a small, coherent line-icon vocabulary. Icons support labels; they do not replace them. Unicode symbols are not used as primary navigation icons.

## Examples

Use **Install required components · 2.39 GB** rather than six unrelated Download buttons. Use **Why this clip** rather than **THE AUDIT**. Use **ClipGauge Local** rather than exposing a runtime implementation name in the first line. When a size is not known, say **Size calculated during setup** or **Size unavailable**, never `0 B` as a placeholder.

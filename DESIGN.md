---
name: Store
description: A precise product shop with open shelves and restrained blue actions.
colors:
  paper: "#fafafa"
  surface: "#fff"
  ink: "#202124"
  muted: "#62646b"
  line: "#dedfe3"
  soft: "#f0f1f3"
  accent: "#3458be"
  accent-hover: "#294798"
  accent-soft: "#edf1ff"
  danger: "#a02d33"
  success: "#286548"
typography:
  display:
    fontFamily: "Manrope, Arial, sans-serif"
    fontSize: "58px"
    fontWeight: 700
    lineHeight: 1.12
    letterSpacing: "-.04em"
  headline:
    fontFamily: "Manrope, Arial, sans-serif"
    fontSize: "44px"
    fontWeight: 700
    lineHeight: 1.18
    letterSpacing: "-.035em"
  title:
    fontFamily: "Manrope, Arial, sans-serif"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1.18
    letterSpacing: "-.025em"
  body:
    fontFamily: "Manrope, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.65
    letterSpacing: "normal"
  label:
    fontFamily: "Manrope, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 700
    lineHeight: 1.65
    letterSpacing: "normal"
rounded:
  control: "6px"
  compact: "4px"
spacing:
  base: "24px"
  compact-gap: "12px"
  page-gutter: "64px"
  mobile-gutter: "20px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "12px 20px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "12px 20px"
  button-danger:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "12px 20px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "11px 14px"
  order-summary:
    backgroundColor: "#eff1f6"
    rounded: "{rounded.control}"
    padding: "28px"
  empty-state:
    backgroundColor: "#f1f2f5"
    rounded: "{rounded.control}"
    padding: "60px 28px 70px"
---

# Design System: Store

## Overview

**Creative North Star: "The Precise Product Shop"**

Store uses a graphite masthead, near-white page and open product shelves. Manrope carries both expressive headings and compact buying controls. The user-selected monochrome challenger is realized with restrained blue actions rather than a fully grayscale palette.

Product identity comes from SKU, category and weight on tonal panels. The interface makes no photographic or promotional claims. Administrative tables share the same controls and typography while keeping management separate from shopping.

**Key Characteristics:**

- Graphite navigation and near-white working surfaces.
- Open shelves with typographic product panels.
- Compact rounded controls and flat, ruled administration.
- Blue actions, green availability and red errors.

## Colors

A neutral working palette supports a restrained action blue. Frontmatter values are normative and retain the CSS custom-property names.

### Primary

- **Action Blue** (`accent`): primary buttons, links, caret and keyboard focus; `accent-hover` deepens interactive states.
- **Soft Blue** (`accent-soft`): informational background for the CSV review notice before any products are imported.

### Secondary

- **Availability Green** (`success`): stock indicators and receipt confirmation.
- **Error Red** (`danger`): destructive actions, invalid fields and unavailable product messages.

### Neutral

- **Paper** (`paper`): page ground.
- **White Surface** (`surface`): inputs and search.
- **Graphite** (`ink`): headings, body text and masthead.
- **Quiet Gray** (`muted`): descriptions and secondary metadata.
- **Divider Gray** (`line`): table rows, summaries and section rules.
- **Soft Gray** (`soft`): table headings, upload area and category hover.

**The Action Blue Rule.** Reserve the strong blue for actions, links and focus; product panels remain tonal.

## Typography

**Display Font:** Manrope, with Arial and sans-serif fallbacks.
**Body Font:** The same family. Locally served regular and bold font files provide the shipped faces; the bold face is declared for weights 600–800.

**Character:** Heavy, tightly tracked headings anchor a compact, readable shopping interface. Supporting text is quieter and prices use tabular numerals.

### Hierarchy

- **Display:** storefront heading at 58px; steps down to 40px below 768px and 36px below 576px.
- **Headline:** standard page heading; forms use 42px on desktop and 34px below 768px.
- **Title:** section headings, with product names at 17px and mobile product names at 14px.
- **Body:** base reading text; detailed supporting text commonly uses 14px and compact metadata 11–13px.
- **Label:** bold field labels; labels stay in natural sentence case. SKU panels use slight positive tracking.

## Layout

The shared container is capped at 1440px with 64px desktop gutters and 24px gutters below 768px. Header height is 96px on desktop, 82px below 768px and 86px below 576px with wrapped navigation.

Bootstrap's row and column system owns the catalogue and form grids. The category rail is hidden below 768px; above it, the rail occupies three columns until 992px and two columns thereafter. Products use two columns below 992px and three above. A native category select replaces the rail on smaller screens. Form introductions and controls stack below 992px, while paired fields stack below 576px. Inventory uses `table-responsive`.

The desktop bag retains its product-specific 350px summary column and 64px gap, stacking below 992px. The product detail layout stacks below 768px. Bootstrap spacing and flex utilities manage shared alignment and grouping.

## Elevation & Depth

Surfaces are flat at rest. Tonal panels, thin rules and open space establish groups. Only the fixed notification uses the source shadow (`0 8px 28px #2021241a`). The bag summary is sticky on desktop and static below 992px.

**The Open Shelf Rule.** Product information sits on the page without enclosing card borders or shadows.

## Shapes

Controls, notices and summaries share compact rounded corners. Smaller category selections and quantity inputs use the compact radius. Product panels have square corners. Status dots, the bag count and receipt mark use circular geometry. Field and secondary-button strokes are thin; the upload target uses a dashed stroke.

## Components

### Buttons

Confident, compact controls. Primary and destructive actions are filled; secondary actions have a quiet border. Primary buttons have a 46px minimum height, an 18 hundredths second background transition and a darker active state. Add-to-bag controls use a transparent background, compact 40px height and graphite hover fill; their text hides below 992px while an accessible product-specific label remains. Disabled controls visibly mute.

### Cards / Containers

Open product shelves combine a typographic tonal panel with metadata, two-line description and a bottom-aligned buying row. Panels vary through three quiet gray families. Empty states use a single centered tonal container with an outlined SVG, clear explanation and recovery action. The order summary uses a pale cool panel and a strong separated total.

### Inputs / Fields

White fields use a thin gray border, generous inline padding and labels above. Shared focus is a blue 2px outline with 4px offset. Search has a 60px desktop minimum height and its own focus-within border and outline. Invalid inputs have red borders, a subtly tinted background and linked error text. Native file selection stays visible inside the upload area.

### Navigation

The graphite masthead carries the heavy Store wordmark, a small pale blue dot, two text destinations and the bag count. The active destination is white with a pale blue underline. Mobile navigation wraps beneath the brand and bag. Categories use soft selected backgrounds, not pills.

### Feedback

Notifications appear near the bottom center with the sole ambient shadow and a short upward entrance. Success and failure notices use semantic tonal fills. HTMX conflict and validation responses remain visible in the target surface; failed requests produce an error notice. Checkout disables its submit control and changes the label while submitting. Reduced-motion preference disables animation, transitions and smooth scrolling.

## Do's and Don'ts

### Do:

- **Do** use the existing Manrope hierarchy and tabular numerals for prices and counts.
- **Do** preserve visible keyboard focus and text labels for fields and errors.
- **Do** use category, SKU and weight to identify product panels.
- **Do** keep mobile controls usable and use the native category select.

### Don't:

- **Don't** invent product imagery, offers or customer claims.
- **Don't** introduce shadows on product shelves or administrative rows.
- **Don't** replace inline SVG icons with text glyphs.


## CSV review state

The import screen retains the form layout and current tokens. A blue-tinted informational notice states that nothing has been imported. Valid and invalid row counts precede an explicit decision heading. A secondary Cancel upload and primary Import valid rows action require no modal or JavaScript. Errors identify logical row, SKU, field, received value and reason, with an accessible scroll region on desktop and full-height reflow on mobile. No valid rows means no primary import action. Success reports imported and skipped counts; cancellation confirms that inventory was unchanged.


## Bootstrap foundation

Bootstrap 5.3.8 is served locally before the application stylesheet. `btn`, `form-control`, `form-select`, `is-invalid`, `invalid-feedback`, `alert`, `table`, `table-responsive`, `row`, responsive columns, flex utilities and `visually-hidden` own shared primitives. The Store palette and type remain authoritative through `--bs-*` overrides. No Bootstrap JavaScript plugin is loaded because the current workflows use native forms and HTMX.

The migration removed 94 custom rule blocks (393 to 299) and reduced the custom stylesheet from 25,346 to 20,853 bytes before any presentation formatting. Bootstrap adds a separate vendor stylesheet; this is a maintenance simplification, not a reduction in total CSS downloaded.

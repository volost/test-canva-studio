# "Sage & Linen" — build spec for the first new design

A private demo: the reference template's structure with every image, colour and sentence replaced.
Reference study: `../ivory-lace/BLUEPRINT.md`; element ids: `../ivory-lace/outline_page2.txt`,
`../ivory-lace/outline_page1_page3.txt`. All frame sizes below are Canva pixels (site width 1366).

## 1. Look

Natural linen and cotton paper, sage green, watercolour eucalyptus and olive leaves, muted gold, soft warm
colour photos (film look, golden hour, muted greens). Calm, airy, no heavy ornament. No text inside any image.

| Role | Colour |
|---|---|
| Text on paper | `#2f3a2c` (deep green-charcoal) |
| Text on photos | `#ffffff` |
| Paper / cards | `#faf7f0`, card `#fbf8f1` |
| Sage (accents, dividers, lines) | `#8a9a7b` |
| Deep sage (buttons frames, icons) | `#5f6f52` |
| Muted gold (small accents) | `#b89b5e` |
| Dress-code swatches | `#5f6f52`, `#a3b18a`, `#f4f0e6`, `#b89b5e` |

## 2. Rules for every image

- **Replacement images are cover-cropped into the existing frame.** So every final file must have exactly
  the frame's aspect ratio: photos are centre-cropped to it, transparent decor is **padded** to it (never cropped).
- **Phones show only the central column** (about the middle third of the 1366 px width in most sections).
  The subject of every photo must sit in the centre; nothing important near the left or right edge.
- White text sits on `photo_hero`, `photo_story`, `photo_registry`, and on the lower middle of `photo_couple`:
  those areas must be mid-dark and calm (darken in PIL if needed), and checked by pasting sample white text.
- People: from behind, hands, or far away — avoid close-up faces.
- Watercolour pieces on white → `pilot/tools/white_to_alpha.py`. Solid objects with highlights (seal, vinyl,
  rings, pin) must NOT go through it (highlights would turn transparent): cut them out by flood-filling the
  near-white background from the image borders, then feather the edge 1–2 px.
- Look at every final file (downscaled) before accepting it; regenerate with another seed or prompt when weak.

## 3. Assets to produce → `study/sage-linen/assets/`

Generated sizes are multiples of 16. "Frame" is the Canva frame the file must match in aspect.

| File | Frame (w×h) | How | Content |
|---|---|---|---|
| `linen_base.png` | — | generate 1536×1536 | flat top-down natural linen / textured cotton paper, warm oatmeal off-white, even light, nothing else |
| `paper_tall.jpg` | 1366×4201 | generate 1536×1536 paper base, mirror-tile to 2048×6298 | fine handmade cotton paper, warm white near `#faf7f0`, very low contrast; one file serves every paper section |
| `envelope_cover.jpg` | 1366×964 | compose in PIL at 2732×1928 | closed envelope seen from above, see section 4 (no seal) |
| `overlay_flap.png` | 1366×964 | compose, RGBA | the flap with its shadow and the seal baked in; transparent elsewhere |
| `overlay_body.png` | 1366×964 | compose, RGBA | the envelope body below the flap line; transparent where the flap is |
| `seal.png` | 160×198 | generate 832×1024, flood-fill cut-out, pad | oval wax seal, sage green wax with an embossed olive branch, slight gloss, top-down |
| `letter_card.png` | 483×800 | compose in PIL at 966×1600, RGBA | arch-top card `#fbf8f1`, thin sage inner line inset 14 px, very soft shadow; transparent outside |
| `sprig_tall.png` | 137×214 | generate 704×1088, alpha, pad | vertical watercolour eucalyptus sprig |
| `wreath_sage.png` | 332×326 | generate 1024×1024, alpha, pad | round watercolour eucalyptus-olive wreath, open centre |
| `wreath_light.png` | 237×232 | from `wreath_sage` | same wreath with all colour set to cream `#f6f1e4`, alpha kept (sits on the hero photo) |
| `divider_leaf.png` | 398×37 | generate 1536×256, alpha, pad | thin horizontal leafy garland |
| `bullet.png` | 82×74 | generate 768×768, alpha, pad | small watercolour pair of sage leaves (timeline marker) |
| `vinyl.png` | 153×154 | generate 1024×1024, cut-out, pad | black vinyl record with a sage-green label, top-down |
| `rings.png` | 356×158 | generate 1344×608, cut-out, pad | two gold wedding rings lying together |
| `pin.png` | 145×254 | generate 704×1216, cut-out, pad | 3D map location pin, matte sage green |
| `photo_hero.jpg` | 1366×964 | generate 1472×1040, crop | close-up of a couple's joined hands, olive grove behind, golden hour; subject dead centre |
| `photo_story.jpg` | 1366×1116 | generate 1344×1104, crop | couple walking away through a field or olive grove, seen from behind; calm darker centre |
| `photo_venue.jpg` | 1366×725 | generate 1568×832, crop | garden ceremony: wooden arch with greenery, rows of chairs, cypress trees |
| `photo_hotel.jpg` | 1366×725 | generate 1568×832, crop | country villa hotel facade with cypress trees, soft light |
| `photo_registry.jpg` | 1366×589 | generate 1632×704, crop | dark moody still life: wrapped gift with sage ribbon and eucalyptus on dark green cloth |
| `photo_couple.jpg` | 1366×725 | generate 1568×832, crop | couple sitting in a meadow seen from behind, warm evening light |

Also write `assets/manifest.json` (per file: pixel size, aspect, frame aspect, alpha coverage where relevant,
source generation, prompt, seed) and `assets/contact_sheet.jpg` (every final file, labelled, transparent ones
on a mid-grey checker, long edge ≤ 1568 px).

## 4. Envelope geometry (section coordinates 1366×964; compose at 2×)

- Body: linen texture over the whole frame, about 4 % darker than the flap.
- Flap: polygon (0,0) → (1366,0) → (1366,60) → (683,610) → (0,60); linen taken from another part or rotation of
  the texture, about 3 % lighter; a hairline darker edge; soft shadow under the edge (blur ≈ 12 px, offset
  ≈ 5 px down, about 35 % black) so the flap reads as lying on the body.
- Optional faint fold lines on the body from the bottom corners towards the centre.
- The wax seal is centred at (683, 623), 160×198, rotated −3.4°. `envelope_cover.jpg` has NO seal (page 1 places
  the seal as its own element). `overlay_flap.png` has the seal baked in at that exact spot.
- `overlay_flap.png` + `overlay_body.png` laid over each other must reproduce `envelope_cover.jpg` plus the seal.
  In the opening animation one layer slides up and the other down.

## 5. Slots (for the Canva pass)

Locator = `<page>-<section>-<element>` (`-<child>` inside a group). Main page = `PBw4SHZw3cbPHqdd`.

| Where | Element | Gets |
|---|---|---|
| Page 1 `PBXlqtRQwJ1yRgrZ-PBGsmwgM1JByC70M` | section background | `envelope_cover.jpg` |
| | `LBKQqWFQphxMY3SP` (seal; carries the link — never delete) | `seal.png` |
| S1 `PBDtBVS3KYL7J9dy` | section background | `photo_hero.jpg` |
| | `LBxkXqpGlkL367LG` | `wreath_light.png` |
| | group `LBmJ0j4Mjn92TQ1W`: `LBCP6sJYgYKMmktZ`, `LBY8BzNn0xWVgW4C` | `overlay_body.png` / `overlay_flap.png` — which child is which must be found out first (see below) |
| S2 `PB74jDrfyLYQSdW6` | background | `paper_tall.jpg` |
| | `LBgS2d724sY07gbF` | `letter_card.png` |
| | `LB17tt1t3vPffMgc` | `sprig_tall.png` |
| | `LBSxjQxNtz3NLXxp` | `vinyl.png` |
| | shape `LBCb5dhKGGjfrwcJ` (stroke → `#8a9a7b`) | `photo_story.jpg` |
| S3 `PBHdqXf19yPGTShP` | background | `photo_story.jpg` |
| | `LBdHhjlFsbyk3zN3` | `rings.png` |
| S4 `PBb0Thf13p3S4fmP` | background | `paper_tall.jpg` |
| | shape `LBVvHXT4HlW7rYjY` (calendar card) | colour `#fbf8f1` |
| | shapes `LBppRmZcWVcQBV5k`, `LBkBn9nXs8sYTQgx` (they hide parts of the countdown widget) | colour of the paper under them |
| S5 `PBdqW6pycbgKqHlx` | background | `paper_tall.jpg` |
| | shapes `LBv2Mlj1BfhRHrGb` and `LBrQhLnD0DwlcBJK` (two stacked copies) | `photo_venue.jpg` (both) |
| | `LB1ltHzGW5CbFHqX`, `LBW2ldpxFPWFmXNR` (two stacked) | `pin.png` (both) |
| | 7 markers `LBpq4C0hJ9HwdzD3 LB4NQ5xmsgN5rcCw LB78ZsBzKlgppzyR LBrFXzXcmcf0cjRV LBLNtMZrtVXp0fbM LBvy8bjYpSTTHn2k LBsylcqx4Zx8nHBw` | `bullet.png` |
| | 6 lines (type `line`) | stroke `#8a9a7b` |
| S6 `PBNxMQnfcNSk5MPk` | background (now empty) | `paper_tall.jpg` |
| | shape `LBrJd9fJBbPxF7vT` | `photo_hotel.jpg` |
| | `LBNrHTGFd2pZ304z` | `divider_leaf.png` |
| | swatch circles `LBzGmgsmwS8NhQ8R LBqW4M0n2WB2VwZp LBXhXCyn5qK3ScDL LBwgQKSyFLpvMjZx` | the four swatch colours |
| S7 `PB0yWdvQxNhGZPZQ` | background | `paper_tall.jpg` |
| S8 `PB8rV2yHB467ffCP` | background | `photo_registry.jpg` |
| S9 `PBl66PTSNPqsDbzG` | background | `paper_tall.jpg` |
| | `LBXbN3cHrJVWcr6c` | `wreath_sage.png` |
| | shape `LBMG4Nm4V6pdyfB0` | `photo_couple.jpg` |
| Page 3 `PBk5WNyktq95LJP9-PBY4z7z7mp3tK5JN` | group `LBXg0nzgTnL94LfC`: `LBCY01218P3HVQSD`, `LBj14xRcFGWTQlbx` | same two overlay files, same mapping as in S1 |

Everywhere: heart dividers (media `MAHA4Q8kRE4`, vector) recolour to `#8a9a7b`; button frames (media
`MAEzNiskiPA`) and the seven timeline icons recolour to `#5f6f52` if they accept it (keep the white one on
the registry photo white); every text that is `#000000` → `#2f3a2c`; white text stays white.

**Which overlay child is the flap.** Not known. Find out on the disposable probe copy `DAHason1g_M`: in the
full-size preview the two halves visibly slide apart; or delete one child there, commit, export page 2 and see
what remains. Then apply the same mapping in the new design (S1 and page 3).

## 6. Wording (for the Canva pass)

Write new English text for every text element — never keep the seller's sentences — close to the original
length so the layout holds. Sample data, used consistently:

- Couple: **Theo & Clara**; monogram letters T and C; date **Saturday, 18 September 2027**, five in the afternoon;
  hero date `18.09.2027`.
- Venue: Villa Oliveto, Val d'Orcia, Tuscany, Italy. Hotels: Casa dei Cipressi, Hotel La Pergola.
- RSVP by 18 July 2027; contact `hello@example.com`.
- Calendar table `LBxhfzk8VVsmFczv` (7 columns Sunday→Saturday, 6 rows): September 2027 starts on a Wednesday,
  so row 1 = `. . . 1 2 3 4`, row 5 ends with 30, row 6 empty (write an empty string into unused cells).
  Month label "SEPTEMBER • 2027". Move the heart marker `LBdkLjZVv73Kb0vD` (42×38) onto the 18th: row 3, column 7.
- Keep "THE … OF", "Save THE Date", "CLICK TO PLAY", "BACK", "book here" style labels but in new words where a
  sentence is involved. Do not touch the form, the YouTube embed or the countdown embed.

## 7. Configurability (owner's requirement, 2026-11-12)

The owner's words: the template must be "максимально конфігурований" ("maximally configurable") — the person who edits it for their own
wedding must be able to change dates, names, addresses and the other needed things. Rules that follow:

1. **Every personal detail is a live text element**, never part of an image (no initials on the seal, no
   lettering in photos or textures).
2. **Personal details appear only where the design needs them.** Paragraphs are written without names, dates
   or place names, so a buyer never has to hunt through body copy. The complete list of places:
   - names — cover, hero, letter signature, thank-you section;
   - monogram letters — hero, thank-you section;
   - wedding date — hero (short form), ceremony line (long form), calendar (month label, grid, heart marker);
   - RSVP deadline; venue name; venue address; map link;
   - seven timeline rows (time + title); dress-code sentence and four swatches;
   - two hotels (name, one-line description, booking link); contact e-mail; gift button label and link;
   - music link, countdown link, the form's questions; all photos.
3. **Room to grow.** A single-line field whose length varies (a name, the venue, a hotel, a date, the month)
   gets a text box as wide as the phone column of its section, centred on x = 683, so a longer value does not
   wrap. Phone-column widths: cover and S1 433, S2 432, S3 571, S4 432, S5 899, S6 975, S7 509, S8 634, S9 576.
   Paragraphs keep free space below them.
4. **Stress test before sign-off**, measured from the data and looked at in an export: names ALEXANDER and
   ELIZABETH, venue "Castello di Montepulciano", address "Strada Provinciale 146, Montepulciano, Italy", hotel
   "Grand Hotel Villa San Michele" — nothing wraps unexpectedly, overlaps a neighbour or leaves the phone
   column. Then the sample values are restored.
5. **Each website page carries a short editing checklist in its notes**, if the connector accepts notes there.
   **Every button is clickable over its whole area**: the element that carries the link (in this skeleton the
   frame image of the gifts and BACK buttons; the two hotel buttons ship without a clickable link and their
   frames lie above the words, so a buyer's link belongs on the frame) must lie above the label text
   (`layer_element` front). Check in the
   full-size preview by listing `a[href]` elements and testing a 3×3 grid of points inside each with
   `document.elementFromPoint` — every link must score 9/9 (the BACK button scored 6/9 before the fix).
6. **Two documents ship with the design:** `fields.json` (every editable field: key, label, section, element
   ids, sample value, how it is edited, recommended maximum length) and `EDITING_GUIDE.md` (the buyer's
   step-by-step guide, in English: text fields, calendar, countdown, map and booking links, photos, music, form).

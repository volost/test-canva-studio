# Ivory Lace Envelope Reveal — template structure

Analysis dated 2026-11-12. Sources: the design `DAHarqlqips` in Canva (read through the connector), the seller's PDF guide
(Honeycloudtemplates, 18 pages), a PNG export of the pages. Raw data:
`raw/page2.json`, `outline_page2.txt`, `export/`, `slices/`, `pdf/text.txt`.
Connector capability checks were run on the copy `DAHason1g_M` ("TEST COPY - Ivory Lace…"); files are in `../probe/`.

Markers: **[data]** — read from the design; **[run]** — verified by an action; **[not verified]** — an assumption.

## 1. Overall structure

A Canva website 1366 px wide, three site pages **[data]**:

| # | Name | What it is |
|---|---|---|
| 1 | ENVELOPE | cover: closed envelope, names, seal, "open". One section, 1366×964 |
| 2 | MAIN PAGE | the site itself: 9 sections one under another, 16082 px in total |
| 3 | REVEAL ENVELOPE | spare copy of the "envelope overlay" (a group of two full-section images) |

The "envelope" mechanic (PDF, p. 13) **[run, 2026-11-12, preview of the copy `DAHason1g_M`]**: the guest sees
ENVELOPE, presses the seal, and goes to MAIN PAGE. The first section of MAIN PAGE is covered by a group of two envelope
images; after about 1 s the top half slides up, the bottom half slides down, and the hero is revealed (a black-and-white photo of hands with
rings, monogram, names). Page 3 keeps an untouched copy of the group: the seller asks to copy it whole, because changing its structure
breaks the animation. The connector **does not show** links on elements or animations — they are visible only in the editor.

## 2. MAIN PAGE sections **[data]**

| No. | Height | Purpose | Background | Main content |
|---|---|---|---|---|
| 1 | 964 | Hero | photo of the couple (portrait, cropped) | monogram in a wreath, "THE Wedding OF", names 72 px, date 11 px — all white; the envelope group sits on top |
| 2 | 1156 | Letter to guests + music | paper texture | "player" (flowers, cover photo, vinyl record, note, "CLICK TO PLAY", transparent YouTube on top); card frame 483×800 with a heading, divider, text, signature |
| 3 | 1116 | The couple's story | black-and-white photo, full width | photo of rings 356×158, script-style heading, 24 px paragraph — white |
| 4 | 830 | Save the Date | paper texture | heading, calendar card 349×360 (7×6 table, heart on the date, paper clip), countdown (embedded tickcounter 363×91) |
| 5 | 4201 | Ceremony + day schedule | paper texture | photo of the venue in a "torn paper" mask 1366×725; venue name 124 px; date; badge-label; divider; 7 schedule rows (heart, dotted line, icon, time, title) at a ≈205 px pitch |
| 6 | 3617 | Dress code + hotels | white | heading 98 px; 4 colour circles in gold rings; hotel photo in "torn paper"; 2 hotels with "book here" buttons |
| 7 | 1734 | RSVP | paper texture | heading, reply deadline, Canva form 510×955, divider, contact |
| 8 | 589 | Gifts | dark black-and-white photo | heading, text, "Amazon" button — white |
| 9 | 1875 | Thank you | paper texture | monogram in a wreath (65 %), photo of the couple in "torn paper", names in white on top, "Thank You", "BACK" button |

Page 1 (ENVELOPE): background — a photo of an envelope with a lace flap; script lettering 36 px; divider;
names 72 px in three lines; wax seal 160×198, rotated by −3.4°, locked; "open" 15 px at the bottom.

## 3. Layout principles

- **Everything is centred.** The x axis = 683 in all sections; no side column, menu or grid.
- **A narrow column on a wide page.** In sections 1–4 the content takes 410–530 px of the 1366; the rest is background.
- **Invisible locked rectangles** (transparency 0) in the centre of almost every section: 432×964 (like a
  9:20 phone screen) in the hero, 899×4201 in the schedule, 975×3617 in the hotels.
- **The template is built for the phone [run, 2026-11-12]:** in mobile preview with "Resize on
  mobile" switched on, each section is shown so that the central column takes the whole screen width; the cover,
  calendar, schedule and form are readable without zooming. The body text in the editor is 14 to 42 px precisely
  because columns of different widths are compressed to a single screen. That the width is set by the invisible rectangles is
  **[not verified]**: that would need removing one and comparing.
- **On a wide screen** the section stretches to the full window width; in a window with other proportions the cover
  background scales separately from the seal, and the seal slips off the tip of the flap **[run]**.
- **Alternating backgrounds:** photo → paper → photo → paper → paper → white → paper → dark photo → paper.
- **Several details repeat:** the same heart divider 5 times, the same button frame 4 times, the monogram
  twice, "torn paper" three times.

## 4. Typography **[data]**; the connector does not return font names

| Role | fontRef | Sizes, px | Where |
|---|---|---|---|
| Display, capitals, thin strokes | `YAFMT2U2kT8,0` | 33–100 | names, section headings |
| Calligraphic script | `YACgEQzTJgs,0` | 36–125 | "Our Love Story", venue names, signature, "Thank You" |
| Body text (grotesque with letter-spacing 0.147, line height 1.75) | `YAFdJjbTu24,1` | 14–42 | paragraphs, "THE", "OF" |
| Schedule time (geometric grotesque, letter-spacing 0.213) | `YAFdJjvw9Ps,0` | 40 | "08:00 AM" |
| Event names and buttons (serif, capitals, semi-bold) | `YAFdJhX-538,0` | 22–28 | "GUEST ARRIVAL", "BOOK HERE" |
| Calendar | `YAFdJi-0PQg,0` | 11–12 | weekdays, numbers |

One use each: `YAGNIKItaEY,0` and `YAFJstPFAd8,0` (monogram letters), `YAFdJnPX3ZE,0` (date in the hero),
`YAD1aHa0r9w,0` ("CLICK TO PLAY"), `YACgEeV8bIQ,0` ("open").

## 5. Palette **[data]**

Black `#000000` (text), white `#ffffff` (text on photos), ivory `#fffdfa`/`#fcfbf7` (cards),
dotted line `#292514`, cover outline `#cabfa9`, dress-code circles `#181818 #545454 #f7f7f3 #948470`.
The colour comes not from fills but from texture: lace, paper, the gold seal, black-and-white photos.

## 6. Images: roles and frame sizes

| Role | Frame in the design | How many | Whose |
|---|---|---|---|
| Envelope (cover) | background 1366×964 | 1 | seller's upload |
| Envelope overlay, 2 layers | 1366×964 each | 2 (+2 on page 3) | seller's |
| Wax seal | 160×198, transparent background | 1 | seller's (not verified) |
| Paper texture | section background, square; in the 4201 px section stretched three times | 5 | seller's |
| Letter card frame | 483×800, transparent background | 1 | seller's |
| Monogram wreath | 237×232 and 332×326 | 2 | seller's |
| Photos: hero, story, venue, hotel, gifts, couple | background or 1366×725 mask | 6 | seller's |
| "Torn paper" mask | Canva shape with a 5226-character outline | 3 | shape with a photo inside |
| Heart divider | 293–554 × 15–28 | 5 | Canva library (vector, recolourable) |
| Note, heart on the calendar, paper clip | small | 1 each | Canva library |
| Schedule icons (7), button frame, gold ring | 70–140 px; 243×114; 146×146 | 7 / 4 / 4 | apparently Canva library (not verified) |
| Gold heart, venue label, ornament | 82×74; 145×254; 398×37 | 7 / 2 / 1 | not verified |

`get-assets` on 12 of the seller's images answered "Not allowed to access this asset" — they cannot be
viewed or taken separately; Canva library elements are available by id.

## 7. Interactivity **[data + PDF]**

- **Music:** an embedded YouTube 491×276 with transparency 0 over the "player" — the guest taps "the record" and hits the video.
- **Countdown:** an embedded tickcounter.com widget; the date is changed on the tickcounter site and the new link is pasted in.
- **RSVP:** a Canva form (name, attendance, meal, guest, number); in the connector data — type `unsupported`.
- **Links:** "book here", "Amazon", "BACK", "open", venue label — set in the editor.
- **Animations:** the envelope opening and, possibly, elements appearing — only in the editor.

## 8. What the connector can do — verified on the copy 2026-11-12 **[run]**

The copy preserves the structure one to one: 141 elements, the same ids, embedded blocks, table, form.

| Action | Result |
|---|---|
| Replace a section background | works; the image crops itself to "fill the whole frame" |
| Replace an image in a frame, including a locked one | works; the frame size stays the same, the excess is cropped |
| Replace a photo inside a "torn paper" mask | works |
| Replace text | works, the font is preserved; the text frame grows downward, neighbours do not shift |
| Colour of text, shape, line | works |
| Recolour a vector library element | works |
| Change calendar cells, including empty ones | works, the table font is preserved |
| Move the form and the embedded countdown | works |
| Insert a Canva library element by id, a shape, text | works; new text — only in the standard font |
| Add a section to MAIN PAGE | **no**: `add_page` creates a separate site page |
| Change section height, choose a font, add a form/video/link/animation, delete a page | no operations available |
| See the result | no thumbnails for pages with sections; only save and export a PNG |

## 9. Not verified

- The sound of the music (the YouTube video is in place in the copy's preview, 491×276; not checked by ear) and form submission
  (the form with all its fields is displayed; I did not submit a test response).
- The role of the invisible rectangles in the mobile view (see section 3).
- Font names: in the page code there are only markers like `YAFMT2U2kT8_0`; the name is visible in the editor panel
  if you click on the text.
- The template's licence terms: they are not in the PDF, they are in the Etsy listing.

## 10. Verified in the preview of the copy after the connector's save (2026-11-12)

Built-in browser, the owner's account, "Mobile" and "Desktop" views (1440×810):
the transition from the cover to the main page, the envelope opening, the text appearing with animation, the YouTube video,
the countdown (shows zeros: the tickcounter link is the same as in the original), the RSVP form, the map link —
all in place. The changes visible in the copy are only deliberate trial edits in sections 2, 4, 5, 6, 7 and the added page 4.

How the envelope behaves:
- On the cover, the only link is the seal (in the copy's preview — one area of 142×171 px with a transition to
  MAIN PAGE). The "open" lettering in the copy is not a link; in the original this was not checked.
- If the preview starts directly from MAIN PAGE, the envelope opens by itself while the page loads
  (verified on the original).
- The small "Preview" side panel shows a frozen closed envelope and does not react to clicks —
  both in the copy and in the original. The opening is visible only in the expanded preview (the button in the panel's corner).

# Trade Invoice Eval Set — Public Source Catalog

**Purpose:** Held-out eval set for a document-extraction model trained on synthetic trade invoices.
Requirement: real-looking trade invoices with visible LINE ITEMS (description, qty, price) + total.
Trades: HVAC, electrical, plumbing, carpentry, roofing, general contracting.

**Research date:** 2026-06-12
**Methodology:** Web search + direct page fetch across major invoice-template vendors, field-service
software galleries, ML/document-AI datasets, and government/academic sources.

---

## Key Finding Up Front

There is **no single public repository of real, filled, multi-trade contractor invoices** that can
yield 30-50 distinct examples out of the box. What exists falls into three tiers:

| Tier                        | What it is                                                                | Real line items?                             | Obtainable                       |
| --------------------------- | ------------------------------------------------------------------------- | -------------------------------------------- | -------------------------------- |
| A — Narrative examples      | Blog/guide pages that write out sample line items in prose or HTML tables | Yes, but not as images/PDFs                  | 5-10 extractable                 |
| B — Vendor sample galleries | Template vendors that show a partially filled preview image               | Partial — layouts real, numbers illustrative | ~15-25 across vendors            |
| C — ML datasets             | Public document-AI datasets containing invoice images                     | Some real, but not trade-specific            | Hundreds of images, wrong domain |

You can realistically assemble **~20-30** usable examples from public sources if you (a) capture
the vendor preview images and (b) pull the narrative examples from blog pages. Getting to 50
with genuine layout diversity is hard; trade-specific invoices are essentially absent from every
open ML dataset surveyed.

---

## Section 1 — Vendor Template Galleries (Tier B)

These vendors publish "sample" or "example" invoice images as marketing assets on publicly
accessible web pages. The preview images show realistic layouts with some populated fields; in
most cases the dollar amounts are illustrative rather than drawn from a real job. They are
not behind a paywall but are copyrighted by the vendor (all-rights-reserved unless noted).
Usage verdict: suitable for a **private, non-commercial eval set** (research fair use); do
not redistribute.

---

### 1. Jobber — Free Invoice Templates (6 trades)

| Field             | Value                                                                                                                                                               |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| URL               | https://www.getjobber.com/free-tools/invoice-template/hvac/                                                                                                         |
| Also covers       | Electrical: https://www.getjobber.com/free-tools/invoice-template/electrical/                                                                                       |
|                   | Plumbing: https://www.getjobber.com/free-tools/invoice-template/plumbing/                                                                                           |
|                   | Roofing: https://www.getjobber.com/free-tools/invoice-template/roofing/                                                                                             |
|                   | Construction: https://www.getjobber.com/free-tools/invoice-template/construction/                                                                                   |
|                   | Contractor: https://www.getjobber.com/free-tools/invoice-template/contractor/                                                                                       |
| What it is        | Field-service SaaS vendor; each page shows one embedded screenshot of a partially filled invoice created with Jobber's software                                     |
| Real line items?  | Partial — the screenshot shows a populated invoice layout with company name, client, invoice #, date, and at least one service line; exact amounts are illustrative |
| Format            | Embedded PNG/WebP image on page; blank PDF downloadable without signup                                                                                              |
| License           | No explicit license stated; Jobber copyright implied. Images are marketing assets.                                                                                  |
| Distinct examples | ~6 (one per trade page); each has a different layout because Jobber's UI changed over product versions                                                              |
| Usability         | HIGH for layout variety; download the embedded preview image from each page                                                                                         |

---

### 2. InvoiceQuickly — Electrician Invoice Example (annotated)

| Field             | Value                                                                                                                                                                                                                                                              |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| URL               | https://invoicequickly.com/blog/electrician-invoice-example                                                                                                                                                                                                        |
| What it is        | Blog article with a **fully populated electrician invoice rendered as an HTML table** — not an image, but all data is present                                                                                                                                      |
| Real line items   | YES — 8 line items including: Panel upgrade labor ($1,800), Journeyman hrs ($1,100), Apprentice hrs ($550), Main breaker panel ($420), Circuit breakers ($144), Conduit/wire/connectors ($385), Permit fee ($145). Subtotal, 6.75% sales tax, and total due shown. |
| Format            | HTML table embedded in page; no PDF image                                                                                                                                                                                                                          |
| License           | © 2026 InvoiceQuickly. All rights reserved.                                                                                                                                                                                                                        |
| Distinct examples | 1 (electrical only)                                                                                                                                                                                                                                                |
| Usability         | HIGH for content; screenshot or render to image to get a real-looking invoice image                                                                                                                                                                                |

---

### 3. InvoiceQuick — Multi-trade template gallery

| Field             | Value                                                                                                                                                                             |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| URL base          | https://invoicequick.com/invoice-templates/                                                                                                                                       |
| Trade pages       | HVAC: /hvac-invoice-template, Plumber: /plumber-invoice-template, Electrician: /electrician-invoice-template, Contractor: /contractor-invoice-template                            |
| What it is        | Template gallery; pages blocked (HTTP 403) during this research session but search snippets confirm they show populated line item examples in text                                |
| Real line items   | Confirmed in search snippets: "Emergency call-out, 2 hrs @ $180/hr = $360", "R-410A 6 lb @ $38: $228", "Diagnostic/Trip Fee: $89", "3/4 inch ball valve $28, 35% markup = $37.80" |
| Format            | Unknown (403 during fetch); likely HTML preview + downloadable PDF                                                                                                                |
| License           | Not confirmed                                                                                                                                                                     |
| Distinct examples | ~4 (one per trade)                                                                                                                                                                |
| Usability         | MEDIUM — access may require a real browser session; content is confirmed in Google snippets                                                                                       |

---

### 4. Bella FSM — Roofing Estimate Examples (3 detailed)

| Field             | Value                                                                                                                                                                                                                                                                                                                                     |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| URL               | https://www.bellafsm.com/roofing-estimate-template/                                                                                                                                                                                                                                                                                       |
| What it is        | FSM vendor page with **3 complete roofing estimate examples** with actual dollar figures                                                                                                                                                                                                                                                  |
| Real line items   | YES — three estimates fully populated: (1) Storm Damage Repair $2,610: "Architectural shingles GAF Timberline HDZ (4 sq) @ $175/sq = $700", drip edge, pipe boots, labor; (2) Full Roof Replacement $21,670: 30 sq tear-off, materials, labor, permits; (3) Commercial TPO Flat Roof $18,400: insulation, membrane, installation, permits |
| Format            | HTML text on page (not a downloadable PDF image); interactive PDF generator requires filling a form                                                                                                                                                                                                                                       |
| License           | © 2026 Bella Solutions, Inc. "Completely free" template but no open license stated.                                                                                                                                                                                                                                                       |
| Distinct examples | 3 (all roofing; 2 residential, 1 commercial)                                                                                                                                                                                                                                                                                              |
| Usability         | HIGH for content richness; render page-section to image                                                                                                                                                                                                                                                                                   |

---

### 5. Projul — Roofing Estimate Examples (3 detailed)

| Field             | Value                                                                                                                                                                                                                                                                                                              |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| URL               | https://projul.com/blog/free-roofing-estimate-templates/                                                                                                                                                                                                                                                           |
| What it is        | Blog post with 3 complete roofing estimate breakdowns with actual figures                                                                                                                                                                                                                                          |
| Real line items   | YES — three estimates: (1) Residential Re-Roof (30 sq): materials $6,445, labor $3,380, equipment $825, O&P → total $13,717.20; (2) Roof Repair: materials $349, labor $552.50, equipment $125, total $1,357.55; (3) Commercial TPO (100 sq): materials $34,490, labor $23,100, equipment $7,350, total $80,006.08 |
| Format            | HTML text on page; separate download page for template files                                                                                                                                                                                                                                                       |
| License           | © 2026 Projul Inc. All rights reserved.                                                                                                                                                                                                                                                                            |
| Distinct examples | 3 (all roofing)                                                                                                                                                                                                                                                                                                    |
| Usability         | HIGH — good variety of scope and scale                                                                                                                                                                                                                                                                             |

---

### 6. SimplyWise — Roofing Estimate Example (1 detailed)

| Field             | Value                                                                                                                                                                                                                                                                                                  |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| URL               | https://www.simplywise.com/blog/roofing-estimate-template/                                                                                                                                                                                                                                             |
| What it is        | Blog post with one named-contractor estimate example                                                                                                                                                                                                                                                   |
| Real line items   | YES — "Johnson Roofing Co." estimate: Tear-off existing shingles 30 sq ($2,400), GAF Timberline HDZ shingles 30 sq ($4,200), Underlayment + ice & water shield ($1,100), Flashing, drip edge, ridge vent ($850), Labor 3-person crew 2 days ($3,600), Disposal + dumpster rental ($475), total $15,940 |
| Format            | HTML text on page; download link to PDF/Excel                                                                                                                                                                                                                                                          |
| License           | © 2026 SimplyWise. All rights reserved.                                                                                                                                                                                                                                                                |
| Distinct examples | 1                                                                                                                                                                                                                                                                                                      |
| Usability         | HIGH — realistic fictional contractor, full breakdown                                                                                                                                                                                                                                                  |

---

### 7. Smartsheet — PDF Construction Invoice Templates

| Field             | Value                                                                                                     |
| ----------------- | --------------------------------------------------------------------------------------------------------- |
| URL               | https://www.smartsheet.com/content/pdf-construction-invoice-templates                                     |
| What it is        | Template repository with **direct PDF download links** for 8+ construction invoice subtypes               |
| Trades covered    | General contractor, plumbing, electrical, HVAC, roofing, painting, flooring, landscaping                  |
| Real line items?  | NO — templates are blank forms; the preview images show layout only                                       |
| Format            | PDF files directly downloadable (no signup required for templates themselves)                             |
| Direct PDF link   | Roofing estimate (blank): https://www.smartsheet.com/sites/default/files/IC-Roofing-Estimate-9256-PDF.pdf |
| License           | © 2026 Smartsheet Inc. All rights reserved. No open license.                                              |
| Distinct examples | ~8 distinct blank templates (wrong for eval — need filled)                                                |
| Usability         | LOW as-is (all blank); HIGH as ground-truth template structure reference                                  |

---

### 8. Invoice Mama — Roofing Invoice Example

| Field             | Value                                                                                                                                                              |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| URL               | https://invoicemama.com/invoice-template/roofing                                                                                                                   |
| What it is        | Template vendor page that claims "a complete roof invoice example filled out with realistic roof replacement invoice details" for a 25-square job totalling $8,750 |
| Real line items   | PARTIAL — confirmed a total ($8,750) and scope (25-square roof replacement) are shown; specific per-line figures not confirmed in page text (images not fetched)   |
| Format            | Preview images in page + downloadable Excel/PDF/Word (no signup for basic)                                                                                         |
| License           | © 2026 Invoice Mama. All rights reserved.                                                                                                                          |
| Distinct examples | 1                                                                                                                                                                  |
| Usability         | MEDIUM — visit page to capture preview image                                                                                                                       |

---

### 9. Build-Folio — Multi-trade Invoice Templates (6 trades)

| Field             | Value                                                                                                               |
| ----------------- | ------------------------------------------------------------------------------------------------------------------- |
| URL               | https://build-folio.com/resources/contractor-invoice-templates/                                                     |
| Also              | Roofing estimate: https://build-folio.com/resources/roofing-estimate-template/                                      |
| What it is        | Contractor software vendor; provides template text with {{placeholders}}; hero image shows sample invoice dashboard |
| Trades covered    | HVAC, roofing, plumbing, landscaping, electrical, remodeling                                                        |
| Real line items?  | NO — placeholder text only, not populated                                                                           |
| Format            | PDF downloadable ("contractor-invoice-templates-2026.pdf")                                                          |
| License           | © 2026 BuildFolio. All rights reserved.                                                                             |
| Distinct examples | 0 filled; 6 blank templates                                                                                         |
| Usability         | LOW as eval source; useful for layout reference                                                                     |

---

### 10. Joist — Invoice Description Examples

| Field             | Value                                                                       |
| ----------------- | --------------------------------------------------------------------------- | -------------------------------- | ------------------------------ | ---------------- | --------------------------------------------- |
| URL               | https://www.joist.com/blog/invoice-description-example/                     |
| What it is        | Blog post listing example line-item text descriptions for multiple trades   |
| Trades covered    | General contracting, plumbing, HVAC, electrical, painting, drywall          |
| Real line items?  | PARTIAL — trade-specific description text only (e.g., "Labor 6 hrs @ $75/hr | Framing wall and installing door | Materials: 2×4s, door hardware | Labor Total $450 | Materials Total $180"); no full invoice image |
| Format            | HTML text                                                                   |
| License           | © Joist Inc.                                                                |
| Distinct examples | ~6 trade-specific text snippets                                             |
| Usability         | LOW as image eval source; HIGH as line-item content reference               |

---

### 11. Joist — Trade-specific Invoice Template Pages

| Field             | Value                                                                                     |
| ----------------- | ----------------------------------------------------------------------------------------- |
| URL               | HVAC: https://www.joist.com/invoice-templates/hvac/                                       |
| Also              | Estimate: https://www.joist.com/estimate-templates/hvac/                                  |
|                   | General contractor: https://www.joist.com/estimate-templates/general-contractor/          |
| What it is        | Template landing pages; each shows one preview image of Joist-generated invoice/estimate  |
| Real line items?  | PARTIAL — preview images show populated layout; specific figures not confirmed from fetch |
| Format            | Embedded preview image; Excel download (no PDF image download)                            |
| License           | © Joist Inc.                                                                              |
| Distinct examples | ~4-6 preview images across trade pages                                                    |
| Usability         | MEDIUM — capture embedded preview images from each page                                   |

---

### 12. InvoiceSimple — HVAC & Air Conditioning Templates

| Field             | Value                                                                                                          |
| ----------------- | -------------------------------------------------------------------------------------------------------------- |
| URL               | HVAC: https://www.invoicesimple.com/invoice-template/hvac-invoice                                              |
| Also              | Air conditioning: https://www.invoicesimple.com/invoice-template/air-conditioning-invoice                      |
|                   | HVAC estimate: https://www.invoicesimple.com/estimate-template/hvac-estimate                                   |
|                   | Carpentry: https://www.invoicesimple.com/invoice-template/carpentry-invoice                                    |
| What it is        | Template SaaS vendor with per-trade landing pages; each shows an embedded preview image of a populated invoice |
| Real line items?  | Likely PARTIAL (403 blocked direct fetch); known to show populated preview images                              |
| Format            | Embedded preview image in page; online generator + PDF export                                                  |
| License           | InvoiceSimple copyright; no open license                                                                       |
| Distinct examples | ~4 (HVAC invoice, AC invoice, HVAC estimate, carpentry)                                                        |
| Usability         | MEDIUM — visit pages directly to capture preview images                                                        |

---

### 13. Housecall Pro — Electrician Invoice Template

| Field             | Value                                                                                                                    |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------ |
| URL               | https://www.housecallpro.com/electrical/templates-calculators/electrician-invoice-template/                              |
| Also              | General contractor: https://www.housecallpro.com/general-contractor/templates-calculators/construction-invoice-template/ |
|                   | HVAC repair: https://www.housecallpro.com/hvac/templates-calculators/hvac-repair-invoice-template/                       |
| What it is        | FSM software vendor template pages; show preview images (blank template tabs, not fully populated)                       |
| Real line items?  | NO — preview images are blank template sections; page text describes what to include                                     |
| Format            | Preview images + Google Sheets / Excel download (requires email signup)                                                  |
| License           | © 2026 Codefied Inc. Free but requires signup.                                                                           |
| Distinct examples | 0 filled                                                                                                                 |
| Usability         | LOW as eval source                                                                                                       |

---

### 14. Workiz — HVAC/Plumbing/Electrical Invoice Generator

| Field             | Value                                                                                                |
| ----------------- | ---------------------------------------------------------------------------------------------------- |
| URL               | https://fsm.workiz.com/p/tools/invoice-generator                                                     |
| What it is        | Interactive browser-based invoice generator for HVAC, plumbing, electrical; generates PDF on the fly |
| Real line items?  | User-entered; no pre-filled sample shown                                                             |
| Format            | Generates PDF in browser                                                                             |
| License           | Proprietary (Workiz)                                                                                 |
| Distinct examples | 0 pre-filled; infinite if you fill them in yourself                                                  |
| Usability         | LOW as passive source; HIGH as a tool to generate synthetic-looking "real" invoices if needed        |

---

### 15. BuildWithDave — Carpenter Invoice & Estimate Templates

| Field             | Value                                                                                                                        |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| URL               | Invoice: https://www.buildwithdave.com/free-tools/downloads/carpenters/invoice                                               |
| Also              | Estimate: https://www.buildwithdave.com/free-tools/downloads/carpenters/estimate                                             |
| What it is        | Contractor-focused resource site; free Excel/PDF carpentry-specific templates                                                |
| Real line items?  | PARTIAL — templates include lumber, materials, carpentry line items per trade norms; not confirmed whether preview is filled |
| Format            | Excel + PDF download                                                                                                         |
| License           | Not stated                                                                                                                   |
| Distinct examples | 2 (invoice + estimate, carpentry only)                                                                                       |
| Usability         | MEDIUM — download and inspect                                                                                                |

---

### 16. Examples.com — Carpenter Invoice Templates

| Field             | Value                                                                                       |
| ----------------- | ------------------------------------------------------------------------------------------- |
| URL               | https://www.examples.com/business/invoice/carpenter-invoice.html                            |
| What it is        | Template gallery with 7 distinct carpenter invoice designs; references external source PDFs |
| Real line items?  | NO — blank templates with column headers (Qty, Description, Amount) only                    |
| Format            | Template images + external PDF downloads (some from .edu/.gov sources referenced)           |
| License           | © 2026 Examples.com. All rights reserved.                                                   |
| Distinct examples | 7 distinct layouts (all blank)                                                              |
| Usability         | LOW as eval source; good for layout diversity reference                                     |

---

### 17. Freshbooks — Contractor Invoice Templates

| Field             | Value                                                              |
| ----------------- | ------------------------------------------------------------------ |
| URL               | https://www.freshbooks.com/invoice-templates/contractor            |
| Also              | Specific trade pages accessible from same domain                   |
| What it is        | Accounting SaaS vendor template gallery; shows 5+ style variations |
| Real line items?  | NO — preview images are blank/minimal design mockups               |
| Format            | Downloadable templates (Word/Excel/PDF); no filled preview         |
| License           | © 2026 FreshBooks                                                  |
| Distinct examples | 0 filled                                                           |
| Usability         | LOW                                                                |

---

## Section 2 — Open ML / Research Datasets (Tier C)

These are publicly accessible datasets used in document-AI research. None are trade-contractor
specific, but some contain real invoice images that could be reviewed for layout diversity.

---

### 18. RVL-CDIP Invoice Subset (Hugging Face)

| Field             | Value                                                                                                                                                    |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| URL               | https://huggingface.co/datasets/chainyo/rvl-cdip-invoice                                                                                                 |
| Also              | Full dataset: https://huggingface.co/datasets/aharley/rvl_cdip                                                                                           |
| Original source   | https://www.cs.cmu.edu/~aharley/rvl-cdip/                                                                                                                |
| What it is        | 19,947 real scanned invoice images extracted from the Legacy Tobacco Document Library (UCSF)                                                             |
| Real line items?  | YES — these are genuine historical business invoices, though from tobacco-industry vendors (office supplies, printing, logistics), NOT trade contractors |
| Format            | Grayscale images, max 1000px on longest side; ~2.1 GB for invoice subset                                                                                 |
| License           | "Other" — derives from Legacy Tobacco Document Library; UCSF terms apply. Widely used in academic research without restriction in practice.              |
| Trade-specific?   | NO — wrong domain (tobacco industry vendors)                                                                                                             |
| Distinct examples | ~20,000 but essentially 0 that are HVAC/plumbing/electrical/roofing                                                                                      |
| Usability         | LOW for trade-specific eval; HIGH as a real-document image pool if you need non-trade invoice layout diversity                                           |

---

### 19. mychen76/invoices-and-receipts_ocr_v1 (Hugging Face)

| Field             | Value                                                                                           |
| ----------------- | ----------------------------------------------------------------------------------------------- |
| URL               | https://huggingface.co/datasets/mychen76/invoices-and-receipts_ocr_v1                           |
| What it is        | 2,238 invoice images with OCR text and structured JSON labels                                   |
| Real line items?  | NO — synthetic documents with fictional company names, realistic layout                         |
| Format            | Parquet (image + OCR text + parsed JSON); 282 MB                                                |
| License           | "More Information needed" — unclear                                                             |
| Trade-specific?   | NO — generic B2B invoices                                                                       |
| Distinct examples | 2,238 images, all synthetic generic invoices                                                    |
| Usability         | LOW for trade-specific eval; useful for synthetic-to-real generalization study but wrong domain |

---

### 20. katanaml-org/invoices-donut-data-v1 (Hugging Face)

| Field             | Value                                                               |
| ----------------- | ------------------------------------------------------------------- |
| URL               | https://huggingface.co/datasets/katanaml-org/invoices-donut-data-v1 |
| What it is        | 501 invoice images annotated for Donut model training               |
| Real line items?  | NO — synthetic/generated documents                                  |
| Format            | Parquet; MIT license                                                |
| License           | MIT                                                                 |
| Trade-specific?   | NO                                                                  |
| Distinct examples | 501 images, all synthetic generic                                   |
| Usability         | LOW for trade-specific eval                                         |

---

### 21. parsee-ai/invoices-example (Hugging Face)

| Field             | Value                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------- |
| URL               | https://huggingface.co/datasets/parsee-ai/invoices-example                              |
| What it is        | 15 real invoice PDFs from SaaS vendors (Google Cloud, Netlify, Calendly, Semrush, etc.) |
| Real line items?  | YES — real invoices with real amounts, but all are SaaS/software companies              |
| Format            | PDF; viewable at https://app.parsee.ai/documents/view/{SOURCE_IDENTIFIER}               |
| License           | MIT                                                                                     |
| Trade-specific?   | NO — software/cloud invoices only                                                       |
| Distinct examples | 15 real PDFs                                                                            |
| Usability         | LOW for trade-specific eval; good for proving real-PDF handling                         |

---

### 22. SROIE Dataset

| Field             | Value                                                                                           |
| ----------------- | ----------------------------------------------------------------------------------------------- |
| URL               | https://rrc.cvc.uab.es/?ch=13 (ICDAR 2019 competition)                                          |
| What it is        | 973 scanned retail receipt images (not invoices); labeled for key-field extraction              |
| Real line items?  | YES — grocery/retail receipts with items, quantities, prices, totals                            |
| Format            | Images + OCR text + JSON labels                                                                 |
| License           | Research use; check ICDAR competition terms                                                     |
| Trade-specific?   | NO — retail receipts only                                                                       |
| Distinct examples | 973 real scanned documents                                                                      |
| Usability         | LOW for trade-specific eval; useful for understanding field-extraction difficulty on real scans |

---

## Section 3 — Government / Institutional Sources

Only one relevant partial hit from the .gov/.edu search:

---

### 23. TemplateNest / BART Gov — Plumbing Materials Invoice

| Field             | Value                                                                                                               |
| ----------------- | ------------------------------------------------------------------------------------------------------------------- |
| URL               | https://certtest.bart.gov/plumbing-materials-invoice                                                                |
| What it is        | A BART (Bay Area Rapid Transit) web page that shows a sample plumbing materials invoice table                       |
| Real line items?  | MINIMAL — only 2 rows: "Pipes, 100, $5.00, $500.00" and "Fittings, 50, $2.00, $100.00" — clearly a demo/placeholder |
| Format            | HTML table on web page                                                                                              |
| License           | Government public content                                                                                           |
| Distinct examples | 1 (extremely minimal)                                                                                               |
| Usability         | VERY LOW — not a realistic trade invoice                                                                            |

No useful filled contractor invoices were found on .edu or .gov domains. University procurement
specs reference invoicing requirements but do not publish filled contractor invoice examples.

---

## Section 4 — Additional Narrative Sources (Tier A)

These pages contain detailed line-item text (suitable for extracting content into your own rendered
invoices) but NOT image/PDF artifacts you can directly use as eval examples.

| #   | URL                                                                     | Trade       | Example detail                                                                                                           |
| --- | ----------------------------------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------ |
| A1  | https://invoicequick.com/invoice-templates/hvac-invoice-template        | HVAC        | "Diagnostic/Trip Fee $89", "R-410A 6 lb @ $38 = $228", "Refrigerant recovery/EPA handling $35"                           |
| A2  | https://invoicequick.com/invoice-templates/plumber-invoice-template     | Plumbing    | "Emergency call-out 2 hrs @ $180/hr = $360", "3/4 ball valve $28, 35% markup = $37.80"                                   |
| A3  | https://invoicequick.com/invoice-templates/electrician-invoice-template | Electrical  | Panel upgrade labor, journeyman hrs, apprentice hrs, circuit breakers (same as #2 in Section 1)                          |
| A4  | https://www.joist.com/blog/invoice-description-example/                 | Multi-trade | Framing wall ($450 labor, $180 materials), plumbing/HVAC/electrical text descriptions                                    |
| A5  | https://www.smartservice.com/blog/electrician-invoice-and-template      | Electrical  | Trip fee $45, labor 1.5 hrs @ $120=$180, GFCI outlet $24, permit $165, inspection recheck $45, 50 ft wire @ $0.95=$47.50 |
| A6  | https://build-folio.com/resources/roofing-estimate-template/            | Roofing     | Auto-calculated: shingle, underlayment, flashing line items from square footage input                                    |

---

## Summary Count and Realistic Assembly Estimate

### What you can realistically obtain (private non-commercial eval set)

| Source                             | Trade(s)                                                      | Obtainable images / renderings   | Quality                       |
| ---------------------------------- | ------------------------------------------------------------- | -------------------------------- | ----------------------------- |
| Jobber template pages (6 pages)    | HVAC, electrical, plumbing, roofing, construction, contractor | 6 embedded preview images        | Partial fill                  |
| InvoiceQuickly electrician example | Electrical                                                    | 1 (render HTML table → image)    | Full line items               |
| Bella FSM roofing estimates        | Roofing                                                       | 3 (render page sections → image) | Full line items, 3 layouts    |
| Projul roofing estimates           | Roofing                                                       | 3 (render page sections → image) | Full line items               |
| SimplyWise roofing estimate        | Roofing                                                       | 1 (render → image)               | Full line items               |
| InvoiceSimple trade pages          | HVAC, carpentry                                               | 2-4 preview images               | Partial fill                  |
| InvoiceQuick pages (if accessible) | HVAC, plumbing, electrical                                    | 3 (if 403 resolves)              | Good line items               |
| Invoice Mama roofing               | Roofing                                                       | 1 preview image                  | Partial fill                  |
| BuildWithDave carpenter            | Carpentry                                                     | 2 templates (download)           | Partial fill                  |
| Smartsmith / narrative sources     | Multi                                                         | 6 text-only (need render)        | Full content, no image format |
| **Total**                          |                                                               | **~28-32**                       | Mixed                         |

### Diversity coverage

| Trade               | # Obtainable        |
| ------------------- | ------------------- |
| HVAC                | 3-5                 |
| Electrical          | 3-4                 |
| Plumbing            | 2-3                 |
| Roofing             | 8-10 (best covered) |
| Carpentry           | 2-3                 |
| General contracting | 2-3                 |

Roofing is over-represented; plumbing and carpentry are thin.

---

## Overall Verdict

**A usable but modest real-invoice eval set is realistically assemblable from public sources.**

Specific findings:

1. **Roofing is the best-covered trade**: 3 sites (Bella FSM, Projul, SimplyWise) publish
   detailed filled estimates with line items in HTML. These alone give you 7 distinct roofing
   examples with realistic material/labor breakdowns.

2. **Electrical has one strong source**: InvoiceQuickly's annotated blog post (#2 in Section 1)
   contains a complete, structured HTML invoice with 8 line items — the highest-fidelity single
   example found. SmartService (#A5) adds another via narrative.

3. **HVAC and plumbing are thin**: Most HVAC/plumbing sources show blank templates or text
   descriptions only. You can assemble 2-3 examples per trade from narrative sources rendered
   to image, but they will share similar layouts.

4. **Carpentry is the weakest**: Only BuildWithDave and Examples.com cover it, and both are
   effectively blank templates.

5. **No open ML dataset covers trade contractors**: RVL-CDIP, SROIE, mychen76, parsee-ai —
   none contain HVAC/plumbing/electrical/roofing invoices. The closest is RVL-CDIP's 20k real
   invoice scans, but they are tobacco-industry vendor documents.

6. **All sources are all-rights-reserved**: No Creative Commons or public domain trade invoice
   images were found. All vendor sample/marketing images carry standard copyright. For a
   **private, non-commercial held-out eval set** (never redistributed), academic fair use applies,
   but you should note this in your project documentation and avoid any redistribution.

7. **Getting to 50 is unrealistic without augmentation**: You can reach ~30 genuine-feeling
   examples by: (a) capturing vendor preview images, (b) rendering the HTML narrative examples
   to PNG, and (c) running 5-10 examples through the Workiz or Housecall Pro generators with
   realistic trade data. The last step produces new artifacts rather than sourcing existing ones.

### Recommended action plan

1. Screenshot/capture the 6 Jobber trade preview images (one per trade page).
2. Render the InvoiceQuickly electrician HTML table to a PNG (browser screenshot or headless).
3. Render the Bella FSM, Projul, and SimplyWise roofing example sections to PNGs.
4. Capture the InvoiceSimple HVAC/carpentry preview images.
5. Download and screenshot the BuildWithDave carpenter templates.
6. For plumbing/HVAC gap: use the Workiz free invoice generator with data from the InvoiceQuick
   narrative snippets (items A1, A2 above) to produce 3-5 additional examples.
7. Total realistic yield: 28-35 images covering all 6 trades, suitable as a held-out eval set.

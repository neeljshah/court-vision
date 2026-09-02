# Licence record -- StatsBomb Open Data (S65; S62 ledger format)

Assessed 2026-09-03. Intended use read against this licence: computing per-team
AS-OF aggregates from the StatsBomb event grain, joining them onto the soccer
gate spine, and scoring calibration mechanisms against a devigged close.

**Verdict: OPEN FOR RESEARCH, CLOSED FOR COMMERCIAL USE AND FOR REDISTRIBUTION.**
The measurement in S65 is permitted. Shipping any StatsBomb-derived column into
a sold or otherwise commercially exploited product is NOT, and the data may not
be committed, published or passed to a third party.

---

## Source

- Data: <https://github.com/statsbomb/open-data> (public, keyless).
  Local cache `data/cache/statsbomb/` (gitignored), 4,235 event files, 13 GB,
  pulled by `scripts/platformkit/data_frontier/statsbomb_open_full.py`.
- Licence document: `LICENSE.pdf` at the repository root
  (<https://raw.githubusercontent.com/statsbomb/open-data/master/LICENSE.pdf>),
  5 pages, "StatsBomb Public Data User Agreement". Read 2026-09-03.
- Document's own version line, verbatim from page 5:

> "StatsBomb Data: User Agreement Standard Terms - last updated 8 September 2023"

- Licensor: StatsBomb Services Ltd, England and Wales company 10377735.
  Governing law: England and Wales.
- Terms also summarised in the repository `README.md` (read 2026-09-03).

## Permitted use -- clause 1.1, quoted

> "Subject to the terms of this Agreement, StatsBomb will provide the User with
> access to the Service to be used for analysis, research and to facilitate the
> shared ideas & understanding of the data"

And from the Agreement's preamble:

> "StatsBomb have made this data freely available and accessible to encourage and
> facilitate research and the shared analytical understanding of the game of
> Football. This is aimed to be a research tool, and is intended to be used as
> such. Any analysis or conclusions that are created as a result of using this
> data, may be shared publicly but are not necessarily the opinions or analytical
> insights of StatsBomb."

Calibration measurement on a frozen corpus is analysis and research. It is inside
clause 1.1.

## Prohibited use -- clause 1.2, quoted

> "The User may not: 1.2.1. edit, distort, distribute, reproduce, sell or in any
> way provide the data to any external or third party; 1.2.2. commercially
> exploit the data or any analysis derived from the use of the Service; 1.2.3.
> use the Service for any activity of an illegal or fraudulent nature, to violate
> any laws; 1.2.4. use the Service to produce, transfer, distribute or publish
> any material that might be defamatory or damaging to any individual or
> organisation 1.2.5. decompile, reverse engineer, or otherwise attempt to obtain
> the source code of the Services;"

And clause 7:

> "The User acknowledges and agrees that all data provided through the Service, is
> the property of StatsBomb. The User shall, except as expressly permitted herein,
> shall not modify, translate, transfer, distribute, license, sell or otherwise
> exploit for any purposes whatsoever any data, content or third party
> submissions or other proprietary rights not owned by the User"

## Required attribution -- clause 1.4, and the README

> "The User is required to accredit any publication of analysis formed from
> StatsBomb Data with the StatsBomb brand logo."

README, verbatim:

> "If you publish, share or distribute any research, analysis or insights based on
> this data, please state the data source as StatsBomb and use our logo, available
> in our Media Pack"

## Requested registration -- clause 2.2

> "StatsBomb asks that all Users provide details of their personal information
> (name and email address only) before they access the Service,
> www.statsbomb.com/resource-centre"

Phrased as a request ("asks that"), not a condition precedent to the licence
grant in 1.1. **Not done as of 2026-09-03** -- flagged for Neel, one form.

## What this means for this repo -- binding

1. **Research measurement: allowed.** The S65 census, and any calibration
   measurement built on this data, is inside clause 1.1.
2. **No commercial use of the data OR of anything derived from it (1.2.2).** No
   StatsBomb-derived column may enter a sold product, a paid service, or any
   wagering activity. This is the widest clause here: it reaches the *analysis*,
   not only the data. Given the platform's stated sellable direction, a
   StatsBomb-derived feature is a licence liability the moment the product is
   commercial, so none was landed (see S65).
3. **No redistribution (1.2.1, 7).** `data/cache/statsbomb/` stays gitignored and
   is never committed, published, or copied to a third-party host. Derived
   parquets built from it inherit the same restriction.
4. **Attribution on publication (1.4).** Any published analysis using this data
   states StatsBomb as the source and carries the StatsBomb logo.
5. **Registration outstanding (2.2).** Neel to register at
   statsbomb.com/resource-centre.

## Relation to the S62 licence ledger

`docs/evidence/LICENCE_LEDGER.md` (S62, landed 0730a4b9e) already carries
StatsBomb as **OK (CONDITIONAL)** on exactly this reading -- clause 1.1 grants
research, clause 1.2.2 flips the row to DECIDE the moment anything
StatsBomb-derived enters a sellable output, and the 1.4 accreditation and 2.2
registration obligations are unmet. That entry and this record were read from the
same PDF independently and agree; this file is the full-clause expansion the
ledger row points at, and it does not change the ledger's verdict. S62's
observation that the PDF's text layer omits inter-word spaces is reproduced here
-- spacing was restored by hand in every quote above and nothing else was altered.

## Disclosure of what was already done before this record existed

The 4,235-file cache was pulled by `statsbomb_open_full.py` before any licence
record was on file (the S62 gap: the repo ingests sources without recording their
terms). Nothing was redistributed, nothing was committed, and no derived column
reached the gate spine. This record closes the clause-level gap for this
source; S62's own ledger keeps StatsBomb as OK (CONDITIONAL) and stays OPEN for
the six DECIDE rows (ESPN/Disney, NBA Stats, MLB StatsAPI, Statcast, FotMob,
YouTube footage) and the twelve UNREAD ones.

Reading it did not create a new fetch: the licence PDF and README were the only
two files retrieved this session, into the scratchpad, not into `data/`.

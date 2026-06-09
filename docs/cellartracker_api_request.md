# Draft: CellarTracker partner API request

Send to CellarTracker support (https://support.cellartracker.com, or the
contact option in your account). Their forum indicates a limited API exists
for select partners while a public registration model is finalized — a polite
use-case description is the right way in. Edit the bracketed parts first.

---

**Subject:** API access request — personal cellar-import tool (read-only wine search)

Hi CellarTracker team,

I'm a CellarTracker user ([your username]) building a small personal tool
that helps me import messy wine inventory spreadsheets into CellarTracker.
The tool cleans and normalizes the rows locally and produces a CSV for your
standard import flow.

The one step I can't do well offline is resolving each wine to its proper
CellarTracker identity (the iWine id), so the import lands on the right
existing wine instead of creating near-duplicates. Today I do this by hand
in the browser. I'd love a sanctioned way to automate just that step:
read-only wine search returning iWine ids and basic wine attributes
(producer, vintage, varietal, appellation).

Volume would be small — typically a few hundred lookups per import, a few
imports per year, results cached locally so wines are never looked up twice.
I'm deliberately not scraping the website; I'd rather do this in a way you're
comfortable with.

I understand from the forums that there's a limited partner API while a
public registration model is being finalized. Is there a way for a personal,
non-commercial tool like this to get access, or a recommended alternative?

Thanks for the great service,
[name]

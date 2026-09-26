# Aphanologia
This repository describes efforts to create a web-based PostgreSQL database for exploring and displaying infomration about soil organisms and other obscure groups in the UK.  The name means "knowledge of hidden things". It is being initially created to host data on Acari, but it is hoped to be adapted and applied to other groups if this is useful.  This repository is under active development and is likely to be a bit messy and possibly will contain scripts that don't fully work.  Thanks for your patience!

### Background
With effort from staff and volunteers, a total of 25,000 records of acari observed in Great Britain, and every entry has now been matched to a valid scientific name according a synonymic taxonomic database i've constructed to support the assignment of records from British mite research, and help generate a national species list. Of the 2479 species of acari thought to be in the UK, i have amassed records of at least one observation of 1653 of these. The remaining species have been listed in more general documents (e.g. international reviews of a taxon group which notes “Great Britain” as a known location, or attempts at past species lists where the sources of the observations aren’t clear.  There are probably also some, like Hermannia scabra, which have been recorded under this name, but all of whose records have been proven to be likely to refer to Hermannia nodosa – I may remove these from the list in due course.  All this data, and other data mentioned below, are currently in an Excel spreadsheet.

This project aims to use these data to form the basis of an online database which will allow people to view and map British observations of acari, at a range of taxonomic levels, download data, view information about species found together in the same sample, view or download photographs of identified specimens, view taxonomic information about the species (other names applied to this species in the UK), get references, or even link to downloadable documents, relating to the species, its observations identification and taxonomy.  The database should also allow superusers to update taxonomic relationships, add additional records, or add other information to the database.  The database should be compatible with, and ideally linked to, the NBN atlas, the UK species inventory and the GBIF.

Various tables were created in excel in preparation for this effort. The headers below are the names of the worksheets

#### Taxonomy
* taxonid:	A unique number relating to the taxon name
* parentNameUsageID:	The unique number of the parent (either a higher parent taxon or the correct name for synonyms or misapplications)
* scientificName:	The binomial or trionomial name.  Subspecies are written as a 3 word trinomial, varieties have the variety name preceded by “var. ” and formas have the forma name preceded by “f. ”
* taxonrank:	The rank of the taxon including kingdom, phylum, class, superorder, order, suborder, infraorder, hyporder, parvorder, microrder, nanorder, superfamily, family, subfamily, genus, species, subspecies, variety, forma.  Note that I have chosen to include names that include subgenera as a “synonym” but included “valid name with subgenus”, to keep the logic clean.
* scientificnameAuthorship:	The name and date of the author that first described the species with names in brackets for instances where the root name is retained or merely adapted, “sensu Name, date” for * misapplications or “non Author, date” for instances where multiple authors have erected the same name independently.
* taxonomicStatus:	Is either “accepted”, “doubtful”, “misapplied” or “synonym”
* nomenclaturalStatus:	may be: invalid - superseded basionym; invalid - junior synonym; invalid - subsequent combination of basionym; invalid - literature misspelling; misapplied; species inquirenda; invalid - subsequent combination of junior synonym; invalid - misspelled or invalid basionym; invalid - misspelled or invalid junior synonym; valid name with subgenus; nomen dubium 
* taxonRemarks:	Notes on synonymy and justification for presence in UK species list, where known

#### Observations
* observationID:  unique reference number. This is the same as that used in previous versions of the AcReS (Acari Recordign Scheme)
* eventID: a linking key to the Samples table below
* taxonID	The linking reference number to the Taxonomy table, relating to the unique taxon name originally recorded, or, if taxonomy manually updated, one that matches the entry (e.g. Macrochelid sp. Original entry might match to the GUID for Macrochelidae, Anoetidae would match to the GUID for Histiostomatidae, Eriophyid sp recorded in 1921 would match to Eriophyoidea because it could now refer to several families etc.date collected min	the earliest date possible for the observation
* identifiedBy: The name of the person identifying the specimen
* identificationVerificationStatus: the confidence we have in the identification - may be unverified, plausible, unlikely, probable, certain etc.
* verifiedBy: The name of the person verifying the identification
* identificationRemarks: free text for notes on the identification process or issues.
* collectionID: the broad type of collection associated with the speciment (e.g. personal collection, LTMN monitoring programme etc.).
* catalogNumber: entry now superseded by observations demographics below.
* basisOfRecord: the type of material providing the observations, e.g. stillphotograph, preserved specimen, COi barcode etc.
* idTechnique: How the specimen was identified, morphological observation, genetics, image recognition etc.
* idReference: Not needed now due to junction table
* idText: general remarks on the occurrence not relating to identification process (e.g. ecology, etc.).

#### Samples
* eventID:      A unique number assigned to each individual sampling event (could be a single observation of a single specimen, a group of specimens observed together, a community extracted by a tullgren extract, or a collection of Tullgren funnel extracts bulked from a single site over a period of a year, if all bulked and reported together.
* samplingLocation: Place name as free text.
* decimalLatitude: latitude (WGS84) in decimal format.
* decimalLongitude: longitude (WGS84) in decimal format.
* coordinateuncertaintyinmeters: radius in metres of estimated area around central recorded point within which sampling event could have occurred
* bngx: British national grid eastings
* bngy: British national grid northings
* gridRef: OS landranger type grid reference
* earliestDateCollected: the earliest possible date for the sample observation in format YYYY-MM-DD
* latestDateCollected: the latest possible date for the sample observation in format YYYY-MM-DD
* habitat: UK Broad habitat type
* SHADe: This is a microhabitat recording system based on a code where Substrates(S) are described by 4 letters (TsSc woud refer to Timber – soft rot Soil clayey, and would refer to a soft rotting piece of wood lying on clayey soil with the organism found at the interface. Humidity regime (H) (a number from 1 to 7 where 7 is continuously submerged, and 1 is continuously dry e.g. stored products), Acidity/Alkalinity (A)– an estimate of the pH to the nearest whole number of the situation where appropriate (normally just for soils compost manures, dung etc.), and DisturbancE (De) – how long this situation has existed (from 7: centuries (including regular cyclic change e.g. tides, forest leaf fall) to 1: more or less constantly disturbed.  Missing or unknown data is represented by “X” or “x” and the elements are separated by hyphens for easy reading (e.g. TsSc-5-6-5 – Soft rotting wood lying on clayey soil that almost never dries out – only after a fully dry month  on pH 6 soil, that has been in place for between a decade and a century). This column also contains other text microhabitats which don’t follow this format.
* microhabitat: free text description of the microhabitat sampled
* samplingProtocol: free text description of the sampling protocol (Tullgren funnel, sieve and pooter etc.)
* samplesizeValue: the size of the sample taken in the units below
* samplesizeUnit:  the units used to describe the sample size (e.g. cm3)
* recordedBy: the name of the person collecting the sample.
* eventRemarks: general notes on the observation – more details on habitat, microhabitat, type of sample taken, associations with other specific animals/plants
* datarestricted: data sharing restrictions data record
* licenceHolder: if data is restricted, who holds the licence
* dataSource: the source of the sample record as free text. May be a publication reference or type of collection (monitoring programme, personal collection, photo posted on facebook group etc.)

#### Observation_Demographics
demographicID: A unique number for each demographic group record within a single observation of a species.
observationID: the reference number linking these to the observations table above.
sex: the sex of the specimens, being male, female, undetermined, mixed
lifestage: the life stage of the specimen being egg, prolarva, larva, protonymph, deutonymph, tritonymph, nymph, juvenile, adult, dead remains, undetermined, sign or gall.
count: the total number of specimens in this demographic group
density: the density of individuals in this demographic group expressed per densityUnit (see below)
densityUnit: the unit of measurement (e.g. m2, 100cm3) within which the density above is expressed.
minCount: the minimum number (where a range, minimum of maximum is given) - may also apply to densities where a density unit is given (e.g. 1-5 per 100cm3)
maxCount: the maximum number (where a range, minimum of maximum is given) - may also apply to densities where a density unit is given (e.g. 1-5 per 100cm3)
countDescription: free text to use where abundance descriptions are given (very numerous, scarce, etc.)

#### Specimens
specimenID: a unique number for each specimen - note that all specimens must first be entered into a demographic group
demographicID: linking referece to the Observation_Demographics table above.
specCount: the number of specimens (usually 1) in the specimen record
specBarcode: the COi barcode of the specimen.
specPhotos: a URL link to a folder where specimen photos can be viewed.
specLocation: the institute or collection where the specimen is held.
specRef: the reference number of that specimen in that collection
specPreservation: the type of preservation (in ethanol, slide mount etc.)
specType: the taxonomic status of the specimen (Holotype, Paratype, Allotype etc.)
specComments: comments on the specimen.

#### Literature
litID: Unique reference number for a publication
articleTitle: title of article or chapter or book in series.
authorName:  the name or names of authors in the format Surname, A.B.. Multiple authors are given seperated by commas, or the last 2 by an ampersand (&).
editorName: the name of the editor in the format A.B. Surname
yearPublished: year of publication
publicationTitle: the name of the journal or book series, or the name of the book, if a standalone publication.
publicationSeries: the number or name of the series of publication
publicationVolume: the number in arabic numerals of the publication volume
publicationIssue: the number in arabic numerals of the publication issue
publicationTotalpages: the total number of pages in the publication (books, pamphlets etc.)
publicationPages: the page range for the article, chapter etc. in the format 23-45
publishedBy: the name and location of the publisher.
publicationISBNorISSN: the ISBN or ISSN reference number of the publication
publicationDOI: the unique DOI refrence of the publication
sourceURL: the URL where the publication is either referenced or available in full
litNotes: free text comments on the publication

#### Taxonomy_Literature_Junction
taxonid: link to Taxonomy table
Type: how this reference relates to the taxon. May be "As used in", "Name first published in", "Presence in UK from" or "Taxonomy or synonymy from"
litID: link to Literature table

#### Sample_Literature_Junction
eventID: link to Samples table
Type: Currently only "Source of record" entries.
litID: link to Literature table

#### Observation_Literature_Junction
observationID: link to Observations table
type:  Currently only "identified using"
litID: link to Literature table 

#### manual_taxonomy_update
observationID: link to Observations table.
revisedtaxonID:  the revised taxonID to be applied to this observation, rather than using the rules in the Taxonomy table.

Many of these tables would benefit from further rearrangement of the data currently in the free text tables, to update SHADe, specimen location, etc.

### Aim and requirements

i) maintain a secure, flexibly query-able record of acari observations in the UK, linked to typical recorder informmation, groupable by samples, linked to relevant literature used to identify, source an observation, or provide taxonomic details, and linked to other data such as photographs, barcodes, etc.

ii) make this database available online in a secure manner, so that ordinary users can view standard query outputs and submit data records for review and (if approved) subsequent inclusion, while super-users can add data to all tables, and maybe hyper users can revise the database schema and architecture.

iii) allow upload of records (either for review or pre-reviewed by superusers), either on the basis of individual observations (which would also generate individual sample eventIDs) or as dataset uploads.
      a) The individual record upload should allow for some flexibility in entry (e.g. they can fill in the eventID details, then add species to the eventID one at a time (e.g. with an "add another observation from this sample" button). It would be good to allow editing before they submit, and also allow them to withdraw and edit any records that haven't yet been verified.
     b) The dataset upload should allow users to select the columns that they can enter from their data, and allow them to generate a template for upload that will already have the correct columns, complete with a metadata page explaining what should go in each column).  I'm guessing that this will smooth the process and encourage people to record useful parameters.

iv) allow casual users to browse taxonomy of British acari, using a dynamic menu that allows them to "drill down" from higher to lower taxa, opening up groups of child taxa offset, and with linking lines, under parent taxa, from Kingdom, all the way down to "forma", and covering all the taxonomic ranks used in acarology, including sub, infra, hyp, parv, micr, and nan-orders.  Under the valid species, these should include a further list of known synonyms.  Each taxon can be clicked on to view taxonomic inofmraiton and notes...  All taxa should be searchable using boolean searches, which will link to any taxonomic entry, accepted or not.

v) When a taxon is selected, the screen will display maps showing the distribution across the UK (the mites of Northern Ireland, however, have traditionally been recorded as part of Ireland, by Tom Bolger and others at UCD).  This should include the channel islands, and Isle of Man, but not other overseas crown protectorates (e.g. falklands etc.)..  The maps should also have some summary data, and controls in their legend, allowing users to set date ranges, or view accuracy radii showing the precision of the record.  Clicking on individual records on the map should bring up their observation data.

vi) the taxonomy pages should scrape photographs from specimen data to display, ideally showing the most "popular" image of the taxon first, then allowing "more photos" to be clicked on to show a full gallery.
Source data

Taxonomic lists initially from Turk, 1953, NHML mite species lists, Gledhill and Viets, Luxton oribatid lists
Records harvested from many sources, including extensive review of past literature and capture from historic published sources.
Some data from recent Natural England research, CEH research etc.
Also personal observations, photos from Facebook group etc.
Data arranged into this final schema of tables ready for a final python script to upload.  I'll give the name of the excel tab where the table is found, then a colon, and then all the headers - let me know if you need to know anything specific about the data under these headers if it's not clear.




Observation_Demographics: demographicID	observationID	sex	lifestage	count	density	densityUnit	minCount	maxCount	countDescription

Specimens: specimenID	demographicID	specCount	specBarcode	specPhotos	specLocation	specRef	specPreservation	specType	specComments



Literature: litID	articleTitle	authorName	editorName	yearPublished	publicationTitle	publicationSeries	publicationVolume	publicationIssue	publicationTotalpages	publicationPages	publishedBy	publicationISBNorISSN	publicationDOI	sourceURL	litNotes

Taxonomy_Literature_Junction: taxonid	Type	litID

Sample_Literature_Junction: eventID	Type	litID

Observation_Literature_Junction: observationID	type	litID

manual_taxonomy_update: observationID      revisedtaxonID

All these tables are represented in a single excel spreadsheet saved to:

C:\path\to\project\AcariUKDatabase\260822_AcReS_Data_Upload.xlsx

# Database setup
The database Aphanologia (meaning knowledge of hidden things) was created using pgAdmin 4 and postGreSQL
(check older AI chats for details)

## Importing data
### Ensure Prerequisites
Open Command Prompt (Win + R, type cmd, hit Enter) and ensure the necessary Python bridge packages are installed:
```
pip install pandas openpyxl sqlalchemy psycopg2 geoalchemy2
```

### Duplicate Primary Key Finder Script
The following script checks for duplicates in the primary key

[duplicate_finder.py](duplicate_finder.py)

### Upload data to database
Checked records were into the database Aphanologia using this import script

[upload_acres_db.py](upload_acres_db.py)

This confirmed:
  ✓ Uploaded 10093 rows into table 'samples'.

  ✓ Uploaded 24991 rows into table 'observations'.

  ✓ Uploaded 4919 rows into table 'observation_demographics'.

  ✓ Uploaded 129 rows into table 'specimens'.

  ✓ Uploaded 8304 rows into table 'taxonomy'.

  ✓ Uploaded 375 rows into table 'literature'.

  ✓ Uploaded 733 rows into table 'taxonomy_literature_junction'.

  ✓ Uploaded 5425 rows into table 'sample_literature_junction'.

  ✓ Uploaded 73 rows into table 'observation_literature_junction'.

🎉 DATABASE STRUCTURE AND DATA UPLOAD COMPLETE!

This verification script was run as an SQL query in pgAdmin 4

[verify_database_structure.sql](verify_database_structure.sql)

This produced the output:
|"table_name"|"total_rows"|"bng_geoms_built"|"wgs_geoms_built"|
|"literature"|375|||	
|"observation_demographics"|4919|||		
|"taxonomy"|8304|||		
|"observations"|24991|||		
|"samples"|10093|10090|8423|

This script was run as a query in pgAdmin 4 to ensure fast spatial queries when connecting to QGIS, bounding box filters, or running spatial joins. It builds GiST spatial indexes and B-tree indexes on the foreign keys:

[BuildSpatial&BtreeIndex_Aphanologia.sql](BuildSpatial&BtreeIndex_Aphanologia.sql)

Once in SQL, the database schema was refined to ensure future compatibility with standard biological database structures and allow flexibility.
The following key standard mechanisms used by major biological record centers (NBN, GBIF, iRecord) were built into the schema extension below:

1.	Identification Key Linkages: Extending taxonomy_literature_junction with matrix flags (is_key, key_coverage_rank, url_link) so users can click a genus/family and immediately get a link to the online key or paper needed to reach species.

2.	Darwin Core / GBIF / NBN Atlas Syncing: Adding fields for gbif_dataset_id, dwc_occurrence_id (UUID), sensitivity_precision (for obfuscating rare species locations if needed), and sync timestamps (last_gbif_sync).

3.	Audit Trail & Verification: A standard NBN status workflow (pending, verified, queried, rejected) attached to every observation, tracking who verified it and when.

4.	Media & Molecular Barcodes: Dedicated tables for photographs (with thumbnail URLs, primary image flags, license/copyright metadata) and DNA barcode sequences (COI, 18S, ITS).

This script was run to effect these changes:

[Update&FutureproofStructure_Aphanologia.sql](Update&FutureproofStructure_Aphanologia.sql)


### Set up FastAPI for web interface
Python scripts are needed to communicate between PostGIS database and the web browser. FastAPI is used here build web applications and APIs (Application Programming Interfaces)linking browser based queries to the local PostgreSQL database, converting the spatial points into a standard web format (GeoJSON), and sending it to the web page to display on a map.

A folder was created in the main working folder called
`Aphanologia_Web`
and inside this folder was created a virtual python environment in the command line

```
python -m venv venv
```

The environment activated in windows powershell - this needs setting up with the following packages :
```
cd "C:\path\to\project\AcariUKDatabase\Aphanologia_Web"
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\venv\Scripts\Activate.ps1
pip install fastapi uvicorn asyncpg psycopg2-binary pydantic sqlalchemy geoalchemy2 authlib itsdangerous python-dotenv httpx
```
to log back into the virtual environment use these commands in powershell:
```
cd "C:\path\to\project\AcariUKDatabase\Aphanologia_Web"
.\venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

# Main database functions script
A central python script containing all main database functions was created in the folder Aphanologia_Web. This was subject to many updates during the process to provide links to new functions and scripts.

[main.py](main.py)

This generated 2 web based interfaces accessible via any browser at the following addresses:

http://127.0.0.1:8000

and

http://127.0.0.1:8000/docs

## Connect FastAPI to PostgreSQL and create that spatial GeoJSON endpoint.
### Step 1: Create a Database Connection Module (database.py)
In the same Aphanologia_Web folder, create a new file named database.py.
Paste the following code into database.py (adjust the password on line 6 if your local PostgreSQL superuser password is set to something other than postgres):

[database.py](database.py)

Create a html file in Aphalolgia_Web called index.html

[index.html](index.html)

At this point [main.py](main.py) was updated to give an interactive map on [http://127.0.0.1:8000](http://127.0.0.1:8000)

Following the provision of a basic dot map at the locaiton above, this was updated to provide expandable clusters

Then an update to both main.py and index.html to allow for dynamic selection of taxa, recording dates, and to toggle the cluster view on or off.

This script imports a list of observations where the taxonomy should be manually overridden, due to past misapplications of names.  this draws on a page in the original upload file containinf the observationID and the revisedtaxonID.

[import_manual_updates.py](import_manual_updates.py)

These were applied in SQL with this query:
[ManualUpdateOverride_Aphanologia.sql](ManualUpdateOverride_Aphanologia.sql)

Some further adjusments were made to seperate out synonym parentage (mapping to accepted species), from parentage of valid taxa, with misapplications being applied to the correct taxa via the observation_taxonomy_override.  There were 3 diagnostics carried out in SQL:

[Diag-A.sql](Diag-A.sql)

[Diag_B.sql](Diag_B.sql)

[Diag_C.sql](Diag_C.sql): Purpose: For every taxon marked misapplied in the Taxonomy table, checks whether all manually-reviewed observations recorded against it (via observation_taxonomy_override) have been corrected to the same target taxon. A single, consistent target across multiple independently-reviewed observations is treated as evidence of a reliable name-to-name mapping (equivalent to a synonym relationship) that can be safely encoded in the Taxonomy table itself. Where overrides for the same misapplied taxon point to different targets in different observations, this confirms the name has been applied in error to more than one real species historically, and must continue to be resolved per-observation rather than via a single taxonomy-level rule.

The following sql script was then applied which Adds a new, unambiguous column to the Taxonomy table that points a synonym or a specifically-pinned ("sensu") misapplied name to its correct accepted taxon, separate from parentNameUsageID (which continues to represent true hierarchical parentage only). Populated for taxonomicStatus = 'synonym' rows, and for taxonomicStatus = 'misapplied' rows whose authorship contains "sensu" (Diag-B/Diag-C confirmed these map consistently). Left NULL for doubtful taxa and for unpinned misapplied names, which remain genuinely ambiguous at the taxonomy level and are resolved only per-observation via observation_taxonomy_override.

[Migration-1.sql](Migration-1.s)

The following script rebuilds view_effective_observations to use the new column
Purpose: Updates the view that resolves each observation's "effective" (correct, current) taxon. Resolution order is: (a) per-observation manual override, if one exists; (b) otherwise, follow acceptedNameUsageID if the recorded taxon is a synonym or pinned misapplication; (c) otherwise, use the taxon as recorded. Also adds a flag identifying any observation recorded against an unpinned misapplied name with no manual override — these should not be treated as resolved, and the flag lets the front end and any future data QA surface them rather than silently guessing.

[Migration-2.sql](Migration-2.sql)

Having tested the data, the main was updated again to effect the following:
* Added a new page route /taxonomy that will serve a new taxonomy.html file
* Added four new /api/v1/taxonomy/... endpoints, one per bullet above.
* Changed the existing map endpoint (/api/v1/observations/geojson) to read from view_effective_observations instead of the raw observations/taxonomy tables, and added a new taxon_id option that uses your descendant-search function. The old taxon_name text search still works too, as a fallback, so the current index.html won't break.

# Taxonomy Browser page
Here's the plan for taxonomy.html, explained before the code so the structure makes sense:

* Left side: the tree. It starts by loading Animalia (via /api/v1/taxonomy/root). Each row has a small triangle (▶) if it has children and/or synonyms to show. Clicking the triangle asks the server for that taxon's children and synonyms and inserts them just below, indented — this is the "lazy loading" we discussed, so it only ever fetches what's actually being looked at.
* Synonyms get their own visually distinct branch — slightly greyed out, italic, with a small "synonym of" label, and no expand arrow of their own (since your data model doesn't nest synonyms further) — exactly the "slightly separated set of branches" you described.
* Clicking the name itself (not the triangle) selects that taxon and loads its full details into a panel on the right, via /api/v1/taxonomy/detail/{taxon_id}.
* A "View on map" button in the details panel links across to your existing map page, pre-filtered to that taxon — this needs one small addition to index.html too (reading a taxon_id from the page's URL when it loads).

[taxonomy.html](taxonomy.html)

A small adjustment to the original script in line 238 allowed clicking on the arrows to instantly retrieve and disply child taxa for the selected taxon.
replacing 
                `childrenContainer.style.display = expanded ? 'none' : 'block';`
with
                `childrenContainer.style.display = expanded ? 'block' : 'none';`

An adjustment to the index.html file allowed it to display the taxon selected in the textbox on the mapping page (index.html) with these lines added to the section 
`\\Build API URL with Query Parameters`

```
				fetch("/api/v1/taxonomy/detail/"+encodeURIComponent(taxonIdFromUrl)) // human written wow! fetches api taxon data
							.then(function(response) { return response.json(); })  // not sure exactly what this line does but it doesnt work without it
							.then(function(json) {document.getElementById("taxonSearch").value = json.scientificName}); // sets value in text box to the scientific name
```

## Adding a taxonomy search facility

This feature needs three new pieces, working together:

* A search endpoint on the backend — since the taxonomy table already holds accepted names, doubtful names, misapplied names, and synonyms all in one place, a single search naturally covers all of them. Basic boolean support is built in: separate alternative searches with the word "OR", and treat multiple words as "must all appear" (AND) by default — e.g. Carabodes minusculus finds names containing both words, Carabodes OR Chamobates finds either. A full boolean parser (nested brackets, NOT, etc.) was not built due to complexity but remains a possibility for later extensions if needed.
* A "path" endpoint — given any taxonID (including a synonym's), this works out the chain of tree branches that need to be opened, from Animalia down to that taxon, so the tree can auto-expand to reveal it.
* Frontend changes — a search box with a live dropdown, and logic to walk that chain, opening each branch in turn, before highlighting the result.

### Get ancestor chain
Purpose: Given any taxonID - including a synonym's - returns the ordered list of taxonIDs from the top of the tree (e.g. Animalia) down to the hierarchical taxon that needs to be expanded to reveal it. If the given taxon is itself a synonym or pinned misapplication, the chain resolves to its accepted name's position in the hierarchy first, since that's where it's displayed (in the separated synonyms branch underneath). This is then used to auto-expand the taxonomy tree to a search result.

[Query-4get_ancestor_chain.sql](Query-4get_ancestor_chain)

main.py was updated by adding new functions from
`import re`

and adding 2 new functions to [main.py](main.py):
* one which Searches every taxon name in the database in one go - accepted
    names, doubtful names, misapplied names, and synonyms all live
    in the same taxonomy table, so this naturally covers all of them
    (aim iv in the project README: 'searchable using boolean
    searches, which will link to any taxonomic entry, accepted or
    not').
    Basic boolean support: the query is split on the word 'OR' into
    separate alternative searches; within each, every space-separated
    word must appear somewhere in the name (an implicit AND).
    e.g. "carabodes minusculus" finds names containing both words;
    "carabodes OR chamobates" finds names matching either.

* another which, given any taxonID - including a synonym's - returns the ordered
    chain of hierarchy taxonIDs from the top of the tree (Animalia)
    down to the hierarchical node that the front-end tree needs to
    expand to reveal it. Wraps get_ancestor_chain() (Query-4).

[taxonomy.html](taxonomy.html) was then updated to include a dropdown box

The following script was added to the mapping page (then called index.html) to fetch the taxon name selected using the dropdown box and pass it to the textbox in the mapping page.

```{html}
fetch("/api/v1/taxonomy/detail/"+encodeURIComponent(taxonIdFromUrl))
    .then(function(response) { return response.json(); })
    .then(function(json) {document.getElementById("taxonSearch").value = json.scientificName});
```
A minor correction was made to ensure that a single click on the taxonomy hierarchy arrows resulted in the rapid display of child taxa, and to reduce the focus on Boolean options in the search box.

Keyboard navigation for the searchbox menu was added to the taxonomy.html page with this script
```
        // Tracks which dropdown row is currently highlighted by the
        // keyboard, so arrow keys can move it up/down and Enter can
        // select whichever one is currently highlighted
        let highlightedIndex = -1;

        searchBox.addEventListener('input', () => {
            clearTimeout(searchDebounceTimer);
            highlightedIndex = -1;
            const query = searchBox.value.trim();
            if (query.length < 3) {
                dropdown.classList.remove('visible');
                dropdown.innerHTML = '';
                return;
            }
            searchDebounceTimer = setTimeout(() => runSearch(query), 300);
        });

        // Moves the keyboard highlight to a specific row index,
        // wrapping round at either end, and scrolls it into view
        function setHighlighted(index) {
            const rows = dropdown.querySelectorAll('.search-result-row');
            if (rows.length === 0) return;
            rows.forEach(r => r.classList.remove('kb-highlighted'));
            highlightedIndex = (index + rows.length) % rows.length;
            const row = rows[highlightedIndex];
            row.classList.add('kb-highlighted');
            row.scrollIntoView({ block: 'nearest' });
        }

        searchBox.addEventListener('keydown', (e) => {
            const rows = dropdown.querySelectorAll('.search-result-row');
            if (!dropdown.classList.contains('visible') || rows.length === 0) return;

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                setHighlighted(highlightedIndex + 1);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setHighlighted(highlightedIndex - 1);
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (highlightedIndex >= 0) {
                    rows[highlightedIndex].click();
                }
            } else if (e.key === 'Escape') {
                dropdown.classList.remove('visible');
            }
        });
```

## Setting up landing page
Header links to the landing page were inserted into the Taxonomy and Mapping broswer so that clicking on the word "Aphanologia" returns you to the landing page.

[main.py](main.py) was adapted to include routing to the landing page:

```
@app.get("/", response_class=FileResponse)
def serve_landing():
    return FileResponse("landing.html")

@app.get("/map", response_class=FileResponse)
def serve_map():
    return FileResponse("index.html")
```
The landing page html was created:

[landing.html](landing.html)

## Fixing Date Filtering
Dates were in plain text YYYY-MM-DD and the date filter on the map wasn't working.  Diagnostics were run in SQL to check the nature of the data.

the get_observations_geojson function in main.py was replaced with this to allow working date selection:
```
@app.get("/api/v1/observations/geojson")
def get_observations_geojson(
    limit: int = Query(5000, description="Maximum number of spatial points to return", ge=1, le=50000),
    taxon_id: Optional[str] = Query(None, description="Filter records to this taxon and everything beneath it (families, genera, species, synonyms, etc.)"),
    taxon_name: Optional[str] = Query(None, description="[Legacy] Filter records by plain text match on scientific name. Prefer taxon_id where possible."),
    start_year: Optional[int] = Query(None, description="Filter records from this year onward"),
    end_year: Optional[int] = Query(None, description="Filter records up to this year")
):
    """
    Queries PostGIS and converts sample/observation points into a
    GeoJSON FeatureCollection.

    Date filtering note: earliestDateCollected / latestDateCollected
    are stored as TEXT (not a true date type), specifically so that
    dates before 1900 can be recorded without issue. They are always
    in YYYY-MM-DD format, so the year is reliably the first 4
    characters - we compare on that directly rather than using
    Postgres's date functions, which only work on genuine date columns.

    Some records only have one of the two date fields filled in
    (e.g. an old record dated only "by 1927"). To avoid silently
    excluding these, we treat whichever date IS present as standing
    in for the other when checking for an overlap with the
    requested year range.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        sql = """
            SELECT
                veo."observationID",
                veo."resolved_scientific_name" AS "scientificName",
                veo."resolved_taxon_rank" AS "taxonrank",
                veo."eventID",
                s."earliestDateCollected",
                s."latestDateCollected",
                s."samplingLocation",
                s."gridRef",
                ST_AsGeoJSON(s.geom_wgs84)::json AS geometry
            FROM view_effective_observations veo
            JOIN samples s ON veo."eventID" = s."eventID"
            WHERE s.geom_wgs84 IS NOT NULL
        """
        params = []

        if taxon_id and taxon_id.strip():
            sql += """ AND veo.resolved_taxon_id IN (
                SELECT taxon_id FROM get_descendant_taxon_ids(%s)
            )"""
            params.append(taxon_id.strip())
        elif taxon_name and taxon_name.strip():
            sql += " AND veo.\"resolved_scientific_name\" ILIKE %s"
            params.append(f"%{taxon_name.strip()}%")

        if start_year:
            # Include the record if its LATEST known date is on or
            # after the requested start year. Falls back to the
            # earliest date if latest is blank.
            sql += """ AND CAST(
                LEFT(COALESCE(NULLIF(s."latestDateCollected", ''), NULLIF(s."earliestDateCollected", '')), 4)
                AS INTEGER
            ) >= %s"""
            params.append(start_year)

        if end_year:
            # Include the record if its EARLIEST known date is on or
            # before the requested end year. Falls back to the
            # latest date if earliest is blank.
            sql += """ AND CAST(
                LEFT(COALESCE(NULLIF(s."earliestDateCollected", ''), NULLIF(s."latestDateCollected", '')), 4)
                AS INTEGER
            ) <= %s"""
            params.append(end_year)

        sql += " LIMIT %s;"
        params.append(limit)

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        features = []
        for row in rows:
            if row["geometry"]:
                feature = {
                    "type": "Feature",
                    "geometry": row["geometry"],
                    "properties": {
                        "observationID": row["observationID"],
                        "scientificName": row["scientificName"],
                        "taxonRank": row["taxonrank"],
                        "eventID": row["eventID"],
                        "earliestDate": row["earliestDateCollected"],
                        "latestDate": row["latestDateCollected"],
                        "samplingLocation": row["samplingLocation"],
                        "gridRef": row["gridRef"]
                    }
                }
                features.append(feature)

        return {
            "type": "FeatureCollection",
            "count": len(features),
            "features": features
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()
```

## Linking images from a taxonomically-arranged image archive
The following script was run to walk through an archive of images where folders have been arranged in taxonomic rank, and individual specimen photos stored within appropriate folders for their level of identification.

 [catalogue_image_archive.py](catalogue_image_archive.py) 

 On the basis of this it was decided to create an extension to the database's observation_media table to allow media to be linked at various levels, whetner sample, observation, observation demographic, specimen or taxon.  This was acheived with a SQL query:

 [Migration-4extend_observation_media.sql](Migration-4extend_observation_media.sql)

Purpose: Adds sample_id, demographic_id, and taxon_id columns to observation_media (which already had observation_id and specimen_id), plus a link_level column recording which single level a given photo is linked at. A database constraint guarantees exactly one of the five ID columns is populated, matching link_level — preventing any row from ever being ambiguous about what it depicts. This supports the full range of real cases: community photos (sample level), population photos (observation level), demographic-group photos, individual specimen photos, and photos that can only be placed at a taxonomic level with no linked record at all (e.g. an unidentified Uropodina of unknown date/location).

The following query was run in sql to ensure that all specimen, observation demographic or observation level photo link allowed for an associated taxon:

[View-1view_media_with_resolved_taxon.sql](View-1view_media_with_resolved_taxon.sql)
Purpose: For every photo, works out its "effective" taxon by walking up the chain appropriate to its link_level — specimen → demographic → observation → resolved taxon (via view_effective_observations, so synonym/misapplication resolution applies here too); demographic → observation → taxon; observation → taxon directly; or the taxon_id itself if that's how it's linked. Sample-level photos resolve to no taxon at all, since a sample is a mixed community, not a single species.

This python script was then run as a "dry run" to import the media archive links:

[import_media_archive.py](import_media_archive.py)

This was later updated to ensure that it was better able to identify "composite" labelled photos (in the filename) and make their display preferential.

This script was run to backfill the already uploaded data to capture composite images

[Migration-5backfill_captions-from_filenames.sql](Migration-5backfill_captions-from_filenames.sql)

Purpose: The initial import stored each photo's specimen folder name as its caption. This updates every existing row to use the actual image filename instead (extension removed), so text-based filtering (e.g. finding "composite" images) works as intended, matching the same logic now used for new imports.

[main.py](main.py) was updated to include functgions to fetch the photos

[taxonomy.html](taxonomy.html) scripts where then upldated to display the photos in the taxon details pane.

a minor fix was applied to index.l so that the map appears more central.

# Setting up user login
It was decided to use google identities because it handles authentication - proving someone is who they say they are, without you ever having to store or manage passwords yourself. It does not handle authorization — knowing whether that verified person is an ordinary visitor, a super-user, or a hyper-user, and what they're allowed to do, which will be handled within the database. So the shape of the system is: Google confirms identity →  database looks up (or creates) a matching user record → that record carries the role → every protected action checks the role from the database.

A google cloud project Aphanologia was set up under the a gmail account.
* Go to https://console.cloud.google.com/
* Create a new project "Aphanologia"
* Navigate to "APIs & Services" → "Credentials" → "Create Credentials" → "OAuth client ID"
* Application type: "Web application"
* set "Authorized JavaScript origins" to http://127.0.0.1:8000
* Set "Authorized redirect URIs," to http://127.0.0.1:8000/auth/callback
  
This provided a get a Client ID and Client Secret

the following packages were installed into the virtual environment using windows powershell:

`pip install authlib itsdangerous python-dotenv`

Credentials, including a session secret key, were saved to an .env file with a gitignore file protecting the .env file

a users table was created in sql running 

[create_users_table.sql](create_users_table.sql)

A login code section was added to [main.py](main.py)

I set up myself as a superuser using this script in sql

`UPDATE users SET role = 'superuser' WHERE email = 'your.email@example.com';`

## Setting up new data submissions
### Individual record submissions
The database structure was updated to allow for new data to be submitted with user info using this sql query

[Migration-6submission_tracking_columns.sql](Migration-6submission_tracking_columns.sql)

There were some issues with some of the Samples columns which were blank on upload, and recorded as double precision when they need to accept text entries.

This script was run to correct the schema:

[Migration-7fix_mistyped_text_columns_in_samples.sql](Migration-7fix_mistyped_text_columns_in_samples.sql)
Purpose: samplingProtocol and samplesizeUnit were created as double precision rather than text, almost certainly because every row's value was blank at the time of the original bulk import, causing Pandas to infer a numeric type. Both columns are meant to hold free text (e.g. "Tullgren funnel", "cm3"). This converts them to text, matching their intended purpose, and is safe since — being all-null — there's no real numeric data to lose in the conversion.

also same problem in observations.  ran this:

[Migration-8fix_mistyped_text_columns_in_observations.sql](Migration-8fix_mistyped_text_columns_in_observations.sql)

At this point it was noticed that not all misapplied taxa had a valid acceptedNameUsageID.  This was because these had been populated using the marker "sensu Name" in the scientificNameAuthor field to indicate where a misapplication had happened.
However, some such references were marked with no modifiers (just an author name or name and date), and others were marked "(lapsus) Name, date" or just "in Name, date" 

This script was run to ensure that all the misapplications were treated at the same rank as synonyms, rather than as valid children int he taxonomy displays.

[Migration-9backfill_acceptednameusage.sql](Migration-9backfill_acceptednameusage.sql)

The form was set up, to allow entry of a sample details and then allow one or more observations to the sample.  This didn't initially include demongraphic and specimen details, so these were added later.  

[submit.html](submit.html)

Earlier versions 

##Database Schema viewer
A new page

[schema.html](schema.html)

was created to allow superusers to view the database structure through the online GUI.

this also involved an update to main.py to add require_superuser, the /schema route, and GET /api/v1/admin/schema).

This shows every table, its live columns (name/type/nullable/default), and its foreign keys, plus a list of views — all read fresh from information_schema/pg_catalog on every page load, never cached or hand-maintained. There's a filter box that searches both table and column names and auto-expands matches, so you can can check field names with text queries.

A review of the schema using the code/page above revealed that many database columns had type mismatches as a result of assmptions that things were text or empty columns were double precision, on import.

Unnamed:3/Unnamed:4 in taxon_literature_junction included 2 working never meant to be part of the upload which were dropped entirely.
A human-coded habitat dropdown code was added to the entry form.

This was acheived using 2 "Migration" scripts, and main.py and submit.html were updated with changes.
[Migration-10add_demographic_and_specimen_sequences.sql](Migration-10add_demographic_and_specimen_sequences.sql)
This allows integration of the observation_demographics table and specimen table, allowing them to be completed through submit.html, including on already submitted samples and observations. Adding a new observation and retroactively from the "Your submissions" list (which, as confirmed earlier, works on already-verified samples too — no restriction). Sex and lifestage are locked to controlled vocabularies; specimen type offers the standard nomenclatural type categories plus "Not a type specimen" as the default-friendly option.

[Migration11type_fixes_dead_columns_and_parent_integrity.sql](Migration11type_fixes_dead_columns_and_parent_integrity.sql)
This removed dead columns and combined parentnameusageid with parentNameUsageID using a diagnose-then-enforce process, checking for NULL parent taxa (shoudl only be Animalia at the top of the tree) with the failsafe being that ALTER TABLE ADD CONSTRAINT will simply fail with a clear error rather than corrupt anything, as an intentional outcome.

Some fixes were applied to the landing page, to link it to the "submit.html" page.  Also a literature display was added to the "taxonomy.html" page, along with necessary style elements, a javascript to retrieve the literature data and an endpoint in main.py

## Review and approval/rejection/reassingment of submitted records
While "observations" already had verification_status/verified_by/verified_date/verification_notes, these are a single snapshot so each new review action overwrites the last, so that gave no record of HOW a record reached its current state, who was involved along the way, or why an earlier decision was changed. Given the emphasis on being able to show your reasoning for taxonomic and verification decisions transparently (to the recording community, to the manager of the UKSI, to anyone questioning a call later), this needs to be a proper append-only log: one row per review action, never overwritten or deleted.

This would also directly supports the planned contributor notification bell (a contributor should be told when one of their records is reviewed) via the viewed_by_contributor flag - not built yet, but the data this needs already exists here rather than being bolted on awkwardly later.

A review page and table was set up to allow review of submitted records by a superuser, which allowed records to be reviewed accepted, rejected or reassigned.  A table records every action, so that there is a clear log of decisions, rather than overwriting decisions. This may allow rollback or an audit trail for decisions.  The new table was created using:

[Migration-12verification_actions_table.sql](Migration-12verification_actions_table.sql) 

and the review page is:
[review.html](review.html)

## Additions and tweaks
Several small fixes were applied:
* Source-of-record picker, above sampling location on the sample form to choose between six categories, picking "Published literature" or "Formal project or survey" reveals a fuzzy-search box against the real tables, with an "add new" fallback if it's not catalogued yet. Everything else gets a plain detail field. The old dataSource[free text] column still gets a sensible human-readable summary written to it automatically, so it stays useful to skim even though the real link now lives in sample_literature_junction / the new sample_project_junction.
* Fuzzy search everywhere it matters — taxonomy browser, submission form's species picker, review screen's reassign picker, and now the map page too. All backed by PostgreSQL's pg_trgm, not a client-side library, so it scales properly as your taxonomy grows.
* Searching for "Nothrus" in the taxon serach box resulted in many "Ameronothrus" populating the list, to the exclusion of the desired species.  This is now fixed — ranking now boosts exact-prefix matches to the top before falling back to similarity score, so the genus itself surfaces first rather than being buried under 15 unrelated genus names that happen to contain the string.
* Map page got the autocomplete it never had — previously it only did free-text substring matching against observation records directly. Now typing brings up the same taxon dropdown as everywhere else; picking a result sets the map to that specific taxon (via taxon_id, descendant-aware) and refreshes immediately. If you type without picking anything, it still falls back to the old free-text behaviour, so nothing's lost.
* Dropdown height bumped from ~220–320px to ~400–440px across all four pages, so more results are visible before scrolling.  Note that on map page this doesn't allow for using keyboard arrows to select from the dropdown yet.

The sample_project_junction requires a project category (survey/monitoring or records-centre bulk download) at creation time, to specifically reflect records-centre downloads distinguishable as a subtype rather than lost as a generic "project." (e.g. ERCCIS as records-centre, England Ecosystem Survey as survey/monitoring). This will be reviewed later.

These were achieved using updates to main.py, index.html, submit.html, taxonomy.html, and review.html, which were updated after creating the new junction table with this script.

[Migration-13fuzzy_search_and_source-of-record_structure.sql](Migration-13fuzzy_search_and_source-of-record_structure.sql)

## Set up superuser taxononmy editing facility

A new admin_activity_log table was inserted into the database in the same pattern as the verification-actions table and web_taxonid_seq was created for new taxonIDs.  This was acheived by running:

[Migration-14_admin_taxonomy_editor.sql]()

To [main.py](main.py) was added, right after the verification-action endpoint:
```
PUT /api/v1/admin/taxonomy/{taxon_id} — full-record save. Validates that reparenting can't create a circular ancestry chain, and that synonymy always points at a genuinely accepted taxon (not another synonym, not a taxon that still has children). Logs a field-by-field diff.
POST /api/v1/admin/taxonomy — create a new taxon (either placed in the hierarchy via a parent, or created directly as a synonym of an existing accepted taxon).
GET /api/v1/admin/activity-log — recent changes, or filtered to one taxon's full history.
New route /admin/taxonomy serving the editor page.
```
A new page [taxonomy_editor.html](taxonomy_editor.html) was created enabling a super user to search a taxon (reusing the existing fuzzy search), edit its fields, reparent or mark-as-synonym via the same search-and-pick pattern as your map page, see its edit history inline, or create a brand new taxon.

A navigation link as added to [review.html](review.html) to the new editor.

Currently there is no delete facility, because reassigning/synonymising covers most of your "senus" typo / merge-duplicate use cases without the FK-cascade risk of deletion. Worth a separate conversation if you actually need it.

Reparenting is blocked if it would create a cycle, and synonymising is blocked if the taxon still has children, which must be reparented first.

### minor snags adjusted

Thanks.  I think we'll not bother with the application of a key across many nested taxa just yet, then.  A couple of other, i hope, minor continuity issues:
1) the gold highlighted superuser buttons only appear on first superuser login, but disappears when the landing page reloads.  Please can they stay for the whole session until the superuser logs out?
2) If you edit a taxon, and click on Save - the whole taxon edit form remains visible.  Please can it close once it's been saved?
3) I'm not seeing any evidence yet of the sidebar with the edits from the session - these should include, i guess all the edits since the user logged in.  Has this been coded, but isn't displaying?
4) Please can the taxonomy page "remember" the state of the tree and the taxon being displayed so that when it's navigated back to  you can carry on working on or around the same group?


1. Gold superuser links disappearing. Found the actual bug: the auth-check <script> in landing.html ran document.getElementById('admin-section') before that <div> existed in the page — it was sitting above the cards in the HTML source. It "worked" the first time by lucky timing (network round-trip slower than parsing) and failed unpredictably after. Moved the script to the end of the body, which removes the race entirely rather than papering over it.

2 & 3. Form not closing / sidebar not appearing. I couldn't reproduce a hard bug in the save logic itself — returnToSearchView() and recordSessionEdit() are both called correctly on a successful save. But I found and fixed two real things that plausibly caused exactly what you saw: a silent data-loss bug where a taxon with a legacy status value not in the new dropdown list (e.g. old free-text like "Accepted") would have that field quietly blanked if saved without being touched, since setting a <select> to a non-matching value just clears it — now the loader detects that and injects the existing value as a selectable option so it's never silently lost. And I made every save outcome — success, "no changes to save", and errors — show up in the prominent banner at the top of the page, not just small text near the button, so if either of the genuinely-correct "stayed open" cases (no changes / a validation error) was what you hit, it'll now be obvious why rather than looking broken. If it still doesn't close after a real edit, the browser console will now also log the underlying error — that'd be the next thing to check.

3 (continued). Session edits persistence. This part was working as coded but was too narrowly scoped — it was a plain in-memory list that reset on every reload, not something that lasted "since login" as you wanted. Switched it to sessionStorage (this is your actual deployed app, not a Claude artifact, so that restriction doesn't apply here) — it now survives reloads and navigation within the same browser tab, clearing only when the tab closes.

4. Taxonomy tree remembering state. Turned out taxonomy.html already had almost everything needed — the search feature's goToTaxon() function already knows how to walk to and expand a taxon's full ancestor chain. I just needed to persist the last-viewed taxon (sessionStorage, saved on every selection) and call that same function on page load. An explicit ?taxon_id= in the URL still takes priority, for deliberate deep links.

5. The process for submitting samples was tweaked to allow the option to choose only valid taxa (useful for new observations and uploads) or to allow all - including synonyms and known misapplications (useful for uploading published literature.
   
## Literature editor

5) i need to be able to browse and edit literature records somehow, perhaps searching from the landing page - browsing is available to all users, uploading new literature records (through the observation upload form) is available to contributors, superusers can delete, or assign literature records to taxa.

Literature browsing/management. New /literature page, plus backend: GET /api/v1/literature (paginated browse+search), GET /api/v1/literature/{lit_id} (full detail, usage counts, linked taxa), PUT/DELETE /api/v1/literature/{lit_id} (superuser-only). Delete is blocked with a clear message if the reference is still cited by any observation, sample, or taxon — no silent orphaning. "Assign to taxa" reuses your existing taxon-literature-link endpoints from the taxonomy editor. One assumption I made: the brief only mentioned browse/upload/delete/assign by role, so I scoped editing existing fields as superuser-only too (contributors can add new entries but not modify others') — flag it if you wanted contributors to have edit rights as well.

Literature widget created:
[literature_widget.js](static/js/literature_widget.js)

I also noticed on this pass that the taxon-search-picker code is now duplicated across index.html, taxonomy_editor.html, and now literature.html — not urgent, but a candidate for extracting into a shared script the same way literature_widget.js works, if you want that cleanup later.

## Editing samples and observations for superusers
The one final element that the superuser now needs is the ability to edit the observations (samples, observations, observation demographics, and specimens).  This will allow me to add more information, make corrections, add literature or project details, delete an observation or duplicate it (e.g. where we have a single observation that actually covers more than one microhabitat etc.). 

That's the full record editor — 25 new backend endpoints, plus a new page at /admin/records (add record_editor.html alongside your other page files, same as the others).

[record_editor.html](record_editor.html)

A few things worth knowing about how it's built:

The microhabitat-split workflow you described works like this: open the sample → Duplicate sample (creates a fresh copy) → edit the duplicate's microhabitat field → open the original observation → Duplicate observation → in the duplicate form, search for the new sample as the target, tick "also copy demographics and specimens" if relevant → done. Two originals stay untouched throughout.

Delete is deliberately layered, not uniform: deleting a sample is blocked outright while any observations still belong to it (they're real scientific records — moving or deleting them is a decision, not a side effect). Deleting an observation, demographic group, or specimen cascades to their genuinely-subordinate children (demographics → specimens → barcodes, media at every level) inside one transaction, and — for observations specifically — shows a preview of exactly what's about to go with it before you confirm.

Verification status is intentionally not editable here. verification_status, verified_by, verified_date, verification_notes stay behind the audited Review Queue workflow you already had — the observation form shows the current status with a link over to /review rather than letting this editor silently bypass that trail. Everything else on an observation (taxon, identification fields, catalog info, remarks, sharing flags, primary literature reference) is editable directly.

Two entry points: search by sample (location/recorder/grid ref/eventID), or search by taxon to browse straight into that species' observations — useful if you're working through a reference and want to check/correct every existing record of a species at once.

## Further tweaks and snags

1. Lat/long bug fixed. Root cause confirmed: samples.decimalLatitude/decimalLongitude are actually text columns in your schema, but I'd typed the edit model as float. The diff was comparing the DB's string "51.234" against a resubmitted float 51.234 — never equal, so it always looked changed. Fixed the model, the geometry-recompute SQL (now casts %s::float8 instead of relying on Python floats), and the frontend (sends plain text instead of parsed numbers).
2. Clickable rows now look clickable. Added a consistent link style (green underline-on-hover) plus a › chevron to every dynamically-loaded row — observations list, demographic groups, specimens, and taxon-search results. Demographic/specimen rows (which expand in place) rotate their chevron to indicate open/closed state; observation rows (which navigate elsewhere) keep a static chevron as an "open" cue.
3. Observation literature Type is now a real dropdown. Added a controlled vocabulary — Identified using, Determination confirmed in, First published record in, Discussed in — validated server-side and offered as a <select> instead of free text. Happy to add more categories if you think of other reasons an observation might cite a publication.
4. set map default to being blnk (no records shown) until a taxon is chosen.
5. Species picker drop down menus were altered in index, taxonomy, taxonomy_editor, record_editor, literature, submit, and review html pages so that scientific name authors were shown alongside species, so that, in cases of misapplication,  it was clearer which entry was the valid species and which was misapplied.

## Record viewer for users
New /records/view page + backend, reachable from a "View Record →" link added to the map popup. It's read-only, public (no login needed), shows sample + observation + demographics + specimens + literature at both levels, and — only for superusers — shows a gold "Switch to editing mode" button linking to /admin/records?observation_id=X. I also taught record_editor.html to accept that ?observation_id= (or ?event_id=) URL param and jump straight to the right record, same pattern as the taxonomy editor's deep links.

[record_viewer.html](record_viewer.html)

## Literature viewer for users
A page was created to allow users to view and select the literature available on the database. This was later updated to include a tab to view and (if user privileges allow) create project infomration, too.

[literature.html](literature.html)

## Bulk upload using template generation

A facility was developed to allow contributors and superusers to upload bulk records based on a template downloaded from the system - this would provide cross validation to ensure uploads met the schema design (samples -> observations -> demographics -> specimens) and would flag any taxon names used that failed to match anything on the database, keeping them as "pending review" but allowing their upload.

This systems doesn't allow upload of observations to existing samples. Only new samples may be committed, which simplifies the download step (no need to expose existing samples as a second reference list).

Whole-batch atomic commit — one transaction, everything or nothing - the entire upload is rejected if it fails to meet the datbase validataion standard - puts the onus on the uploader to get it right.

Unmatched taxon names never block the upload — this simplifies the design rather than complicate it. Instead of a whole new staging table and a second review workflow, an unmatched name just leaves taxonID blank on that observation and stores the typed text in a new `proposed_taxon_name column` — then it surfaces as a filter on the existing Review Queue and gets resolved using the existing taxon picker and "Add new taxon" flow. This required one small migration, one filter added to an existing page, and no parallel system to maintain.

It was decided that superuser uploads should skip review (not taxonomic review, though), and all levels (samples, observations, demongraphics, specimens) of upload should be processed in a single upload, since this data is usually available at upload time, and avoids later fiddly matching of later information to specimens (althought this is possible through a migrate, i suppose).

Template generation (GET /api/v1/batch/template) — builds a real multi-sheet .xlsx on the fly: Instructions, Samples, Observations, optionally Demographics and Specimens, and a Taxon Lookup reference sheet. Sample/Observation/Demographic Ref columns are proper Excel Tables with dropdown validation pointing at each other, so the cross-sheet linking is genuinely robust in Excel, not just theoretically so.

Validate → Commit, two separate endpoints as planned, with the commit endpoint re-running the exact same validation before writing anything.

The Review Queue's observation list used an inner join to taxonomy, meaning any placeholder observation (no taxon yet) would have silently vanished from the queue entirely rather than showing up for review. This was fixed to a left join, since this is exactly the scenario batch upload now creates routinely.
Assigning a taxon to a placeholder observation (via the Record Editor or the new Review Queue picker) now correctly clears proposed_taxon_name once resolved, so it doesn't linger in the unresolved-taxa list after being handled.

Review Queue got a new "Unresolved taxa" section — lists every observation with an unmatched name regardless of verification status (important since superuser batch uploads are auto-verified but can still have genuinely unresolved taxa), with inline "assign existing taxon" search and a "create as new taxon" link that pre-fills the Taxonomy Editor's add-new form via the same ?new_taxon_name= pattern already used elsewhere for deep links.  A small initial issue, which resulted in reassigend taxon observations losing their original data on update, was resolved and issues in the data corrected.

One scope note, consistent with keeping this simple: the Samples sheet captures sourceCategory as free text/dropdown rather than a structured literature/project ID link (picking a specific existing literature reference by ID in a spreadsheet cell isn't practical) — if a batch-uploaded sample needs a proper linked reference, that's a quick follow-up in the Record Editor's already-built sample literature/project panel.

A further set of edits was required to pre-populate donwloaded tables with literature links or information on the project, recording event, museum collection/institutional collection, personal collection or other event where the uploaded records would come from.  This removes the need to individually update each sample with this information after upload and locks each upload to a literature source or project

The addition of a placeholder name for taxon names not present in the database was included using:

[Migration-15batch_upload_taxon_placeholder.sql](Migration-15batch_upload_taxon_placeholder.sql)

Edits were also made to [main.py](main.py), [review.html](review.html), [taxonomy_editor](taxonomy_editor), [landing.html](landing.html) and [submit.html](submit.html)

And a new page created:

[batch_upload.html](batch_upload.html)

A problem relating to a split() function being applied to integer values in the unique identifiers columns was sorted. Problems loading the review page were fixed.  A problem with the taxon reassignment for non-matched taxa from bulk uploads (wiping all data when superusers reassigned taxa) was fixed (was it?  ongoing...)

## Sample submit/edit form harmonisation and update

Submit and record_editor forms didn't consistently use dropdowns and had different available fields to submit or edit.  To harmonise this, the following updates were applied.  Dropdowns, when replacing free text fields only enforce validation on entry or edit, but will tolerate existing values if retrieved.  The SHADe picker was turned into a widget accessible from both submit and edit records for samples.

Sampling protocol was converted into a dropdown on both, allowing values of "Baermann extraction", "Beat sampling", "Bottle trap", "Casual collection", "Collected from host", "Direct observation", "Dispersal and manual selection", "Flotation", "Ground water sampling", "Kick sampling", "Malaise trap", "Other", "Pond net", "Pan trap", "Pitfall trap", "Scrapings/Washings", "Sediment flushing", "Sieve and pooter", "Subterranean pitfall trap", "Surface brushing", "Sweep netting", "Tow netting",  "Tullgren funnel", "Vacuum sampling", "Whitehead Tray", "Winkler bag". This field is nullable.

Date picker dropdowns were applied to both Earliest Date/Latest Date in both submit and edit forms (ensuring that both remained capable of receiving dates pre 1900).

"Recorded by": In the submit form:"Your name" in the box changed to "Name of recorder/collector".

Habitat:  This already had a dropdown in the submit but not in record_editor,  Please can we include a dropdown in record_editor.  Expand habitat options in both to include all current options but also add the following marine habitats (loosely based on JNCC biotopes, but simplified for recording scheme):  Littoral Rock and Hard Surfaces; Littoral Sediment; Littoral Mobile Stones; Open Water (Coastal); Open Water (Offshore); Sublittoral Sunlit Rocks, Reefs and Structures; Kelp forests; Sublittoral Sunlit Sediments; Sublittoral Sunlit Mobile Stones; Seagrass beds; Deeper Rocks, Reefs and Structures; Deeper Marine Sediments.  I've missed "deeper mobile stones" as i'm not sure these really exist in any create quantity.

SHADe:  to add the SHADe picker box to the editor, as well as the record submission, it was created into a javascript widget, similar to that used to add new literature.

Other changes requested were :Sample size value: Add to submit form - accept only numbers; Sample size unit: Add to submit form - only pop up if sample size value is entered, then make it required for submission.  We're looking for everything from vague "sample", "handful" to precise "g", "cm3" here; Data restricted: Add to submit form - as a tick box resulting in a "Y" or "N" value added to the samples table column; Licence holder: Add to submit form - only pop up if data restricted = Y, then make it required for submission; Data source: This is a remaining free text form, and needs to point out that it's not a substitute for adding a real literature link. Change name to "Data source notes" and include in submit; Event remarks/General remarks:  harmonise under General remarks in both forms; Submit also needs a "Cancel" button next to the submit button that just takes you back to the landing page, after a check "Are you sure you want to cancel?  All data entered will be lost." window.

This involved updates to main.py, submit.html, record_editor.html and generated 2 javascript elements shade_widget.js and 

Superuser buttons were added to the taxonomy browser page next to the "Edit taxon" button to "Add child taxon" and "Add synonym", populating the resulting add taxon page with the appropriate parent or synonym details.  During this process the list of acceptable ranks was updated and finalised across the app.

"Coordinate uncertainty in metres" was showing up as an editable field in the observations editing and submission form (as variable 'coordinate_uncertainty_meters' record_editor.html) - with a default value of 100. However, this should be drawn solely from the sample data (where it appears as 'coordinateuncertaintyinmeters'), and can't be changed for individual observations. The field was removed from all releveant forms, and the database queried to ensure that the column contained no useful data - it didn't.  The column was fully nulled, but left if place in case of any legacy issues.

On the mapping page index.html  - selecting a synonym retrieved no records, only entering a valid species in the "Taxon to Map" box resulted in a map of records being generated.  The page was adapated so that when synonym is entered in the search box and "Apply Filters & Refresh Map" is that it looks up and automatically changes to the accepted name, and text appears under the input box: "Showing all records for accepted taxon name." followed by a clickable text underneath: "Search only for <NAME_ENTERED> (synonym) records"), clicking on this will narrows the search to just observations recorded under that name so you can pinpoint synonyms (and misapplications) more easily.  When a synonym only is chosen, the text above it is updated to show that only that synonym's record is being displayed.

In effecting this change, another legacy column issue occurred with "acceptedNameUsageID" and "acceptednameusageid".  The latter term was found to be completely obsolete and should not be used.

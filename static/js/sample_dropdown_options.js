/*
 * sample_dropdown_options.js
 * -----------------------------------------------------------------
 * Single source of truth for the dropdown lists shared between the
 * contributor forms (submit.html) and the superuser record editor:
 * Habitat, Sampling protocol, and the three observation lists
 * (identification confidence, basis of record, identification
 * technique). Any future addition only needs to happen in this one
 * file.
 *
 * main.py also READS the three observation lists from this file when
 * the server starts, and rejects values that aren't in them, so the
 * lists are enforced on the server as well as shown in the forms.
 * Keep each of those three lists as a plain array of double-quoted
 * strings (const NAME = [ "a", "b" ];) so the server can read them.
 * Existing records holding older wording stay editable: an unchanged
 * old value is always accepted.
 */
(function (global) {
    const HABITATS = [
        "Broadleaved and Mixed Yew Woodland",
        "Coniferous Woodland",
        "Boundaries and Linear Features",
        "Arable and Horticulture",
        "Improved Grassland",
        "Neutral Grassland",
        "Calcareous Grassland",
        "Acid Grassland",
        "Bracken",
        "Dwarf Shrub Heath",
        "Fen, Marsh, Swamp",
        "Bog",
        "Rivers and Streams",
        "Standing Open Waters, Canals and Ponds",
        "Montane",
        "Inland Rock",
        "Urban",
        "Supra-littoral Rock",
        "Supra-littoral Sediment",
        "Littoral Sediment",
        "Sea",
        "Mosaic",
        // Marine habitats - loosely based on JNCC biotopes, simplified for recording purposes
        "Littoral Rock and Hard Surfaces",
        "Littoral Mobile Stones",
        "Open Water (Coastal)",
        "Open Water (Offshore)",
        "Sublittoral Sunlit Rocks, Reefs and Structures",
        "Kelp forests",
        "Sublittoral Sunlit Sediments",
        "Sublittoral Sunlit Mobile Stones",
        "Seagrass beds",
        "Deeper Rocks, Reefs and Structures",
        "Deeper Marine Sediments",
    ];

    const SAMPLING_PROTOCOLS = [
        "Baermann extraction", "Beat sampling", "Bottle trap", "Casual collection",
        "Collected from host", "Direct observation", "Dispersal and manual selection",
        "Flotation", "Ground water sampling", "Kick sampling", "Malaise trap", "Other",
        "Pond net", "Pan trap", "Pitfall trap", "Scrapings/Washings", "Sediment flushing",
        "Sieve and pooter", "Subterranean pitfall trap", "Surface brushing", "Sweep netting",
        "Tow netting", "Tullgren funnel", "Vacuum sampling", "Whitehead Tray", "Winkler bag",
    ];

    // Confidence the identifier has in their own identification. Whether
    // someone ELSE has checked the record is tracked separately by the
    // review workflow, so there is deliberately no "unverified" option.
    const IDENTIFICATION_CONFIDENCE = [
        "certain", "probable", "plausible", "unlikely",
    ];

    const BASIS_OF_RECORD = [
        "Preserved specimen",
        "Slide mount (uncleared)",
        "Slide mount (cleared)",
        "Direct observation",
        "Still photograph",
        "Video",
        "SEM image",
        "Environmental DNA (trace)",
        "Metabarcoding",
        "Sign (e.g. gall)",
    ];

    const ID_TECHNIQUES = [
        "Morphological identification",
        "Genetic identification",
        "Automated image recognition",
    ];

    global.SampleDropdownOptions = {
        HABITATS, SAMPLING_PROTOCOLS,
        IDENTIFICATION_CONFIDENCE, BASIS_OF_RECORD, ID_TECHNIQUES,
    };
})(window);

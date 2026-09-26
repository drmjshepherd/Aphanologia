/*
 * sample_dropdown_options.js
 * -----------------------------------------------------------------
 * Single source of truth for the Habitat and Sampling protocol
 * dropdown lists, shared between the sample submission form and the
 * record editor's sample panel. Written here once so the two forms
 * can't drift back out of sync with each other the way they had
 * before - any future addition to either list only needs to happen
 * in this one file.
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

    global.SampleDropdownOptions = { HABITATS, SAMPLING_PROTOCOLS };
})(window);

/*
 * shade_widget.js
 * -----------------------------------------------------------------
 * Shared, embeddable SHADe (Substrate/Humidity/Acidity/Disturbance)
 * microhabitat code builder. Written once here so the sample
 * submission form and the record editor's sample panel both get the
 * same step-by-step builder (major/minor substrate, optional second
 * interface substrate, humidity, acidity with a plant-name lookup,
 * disturbance) rather than maintaining two copies.
 *
 * Usage:
 *   const handle = ShadeWidget.mount(containerEl, {
 *       initialCode: existingCodeOrNull,
 *       onChange: (code) => { ... }  // code is a complete string, or null while incomplete
 *   });
 *   handle.setCode('TsXx-5-6-5');  // re-populate the builder from a code string
 *   handle.getCode();              // current code, or null if incomplete
 *
 * setCode() is defensive: a code that isn't in the expected
 * <sub1><sub2>-<humidity>-<acidity>-<disturbance> shape (e.g. an
 * old/manually-typed value that predates this builder) just leaves
 * the builder's own fields blank rather than throwing - the raw text
 * is never touched by this widget, only offered as a starting point.
 */
(function (global) {
    const STYLE_ID = 'shdw-styles';

    const SHADE_SUBSTRATES = {
        S: { label: "Soil - mineral soil or sediment", subs: { s: "Sandy", c: "Clayey", z: "Silty", l: "Loamy", o: "Organic", b: "Subsoil" } },
        O: { label: "Organic matter (excl. living/woody/dung)", subs: { f: "Fresh cut plant material (e.g. grass clippings)", d: "Decomposing plant material", h: "Humified plant material (no recognisable remains)", b: "Broadleaved leaf litter", c: "Conifer (needle) litter", n: "Nest material of animals", s: "Dried stored food products", p: "Peat" } },
        I: { label: "Inert man-made material", subs: { p: "Plastic / rubber", m: "Metal", o: "Other" } },
        L: { label: "Lichen", subs: { c: "Crustose lichen", n: "Non-crustose lichen" } },
        P: { label: "Plant (non-woody, living)", subs: { l: "Leaves of living plants", r: "Roots of plant", f: "Flowers or fruit", s: "Stems or axils" } },
        F: { label: "Fungi (non-lichenised)", subs: { f: "Fruiting bodies", m: "Fungal mycelium" } },
        E: { label: "Exposed to air", subs: { a: "Aerial / Aeolian sample", s: "Surface of other substrate" } },
        C: { label: "Carrion (dead animal material)", subs: { i: "Dead invertebrate", v: "Dead vertebrate (flesh)", f: "Animal fur, feathers, scales etc." } },
        T: { label: "Timber (all woody material)", subs: { l: "Living woody tissue", u: "Unaltered dead wood (e.g. heartwood)", s: "Soft rot (brown rot) wood", w: "White rot wood", f: "Comminuted wood / invertebrate dung (frass)", b: "Bark (incl. living trees)", t: "Treated wood", c: "Charred wood / charcoal", a: "Ash" } },
        D: { label: "Dung", subs: { c: "Carnivore dung", h: "Herbivore dung", o: "Omnivore dung", i: "Insectivore dung", m: "Manure" } },
        A: { label: "Animals (living)", subs: { a: "Arthropods", i: "Other invertebrates (e.g. molluscs)", v: "Vertebrates" } },
        B: { label: "Bryophytes / lower plants", subs: { m: "Mosses", l: "Liverworts", a: "Algae (excl. marine)", s: "Marine algae (seaweed)" } },
        R: { label: "Rock", subs: { b: "Boulders / bedrock", c: "Cobbles", g: "Gravel", a: "Artificial rock-like material (concrete/brick/tile)" } },
        W: { label: "Water", subs: { r: "Running freshwater", s: "Still freshwater", b: "Brackish", m: "Marine" } },
    };
    const SHADE_HUMIDITY = [
        [1, "1 - Perpetually dry (only moisture from surrounding air)"],
        [2, "2 - Wetted occasionally, dries fully within a day"],
        [3, "3 - Occasionally wetted, dries fully within a dry week"],
        [4, "4 - Stays moist except in unusual drought"],
        [5, "5 - Stays moist in all conditions, including drought"],
        [6, "6 - Occasionally waterlogged"],
        [7, "7 - Continuously waterlogged"],
        [0, "0 - Unknown / not estimated"],
    ];
    const SHADE_DISTURBANCE = [
        [1, "1 - Up to 1 day ago, or constantly disturbed"],
        [2, "2 - 1 day to 1 week ago"],
        [3, "3 - 1 week to 1 month ago"],
        [4, "4 - 1 month to 1 year ago"],
        [5, "5 - 1 year to 1 decade ago"],
        [6, "6 - 1 decade to 1 century ago"],
        [7, "7 - A century or more ago (effectively undisturbed)"],
        [0, "0 - Unknown / not estimated"],
    ];
    const SHADE_PLANT_PH = [
        [4, "Cotton grasses (Eriophorum vaginatum / angustifolium)"], [4, "Crowberry"], [4, "Scots pine"],
        [4, "Sphagnum"], [4, "Cladonia"], [4, "Sickle moss"], [4, "Cross-leaved heath"], [4, "Deer-grass"],
        [4, "Bilberry"], [4, "Ling (heather)"], [4, "Hypnum cupressiforme"], [4, "Wavy hair-grass"],
        [5, "Mat-grass"], [5, "Heath bedstraw"], [5, "Star sedge"], [5, "Tormentil"],
        [5, "Heath/meadow wood-rush"], [5, "Barbed-wire moss"], [5, "Velvet bent"], [5, "Bracken"],
        [5, "Foxglove"], [5, "Common star-moss"], [5, "Bluebell"],
        [6, "Meadow foxtail grass"], [6, "Cuckoo-flower"], [6, "Common sorrel"], [6, "Common cat's-ear"],
        [6, "Thyme-leaved speedwell"], [6, "Common mouse-ear"], [6, "Meadow buttercup"],
        [6, "Creeping buttercup"], [6, "Marsh bedstraw"], [6, "Lesser stitchwort"],
        [6, "Wavy/hairy bitter-cress"], [6, "Sticky mouse-ear"],
        [7, "Broad-leaved dock"], [7, "Dandelion"], [7, "Curled dock"], [7, "Timothy grass"],
        [7, "Yellow trefoil"], [7, "Common vetch"], [7, "Yellow vetchling"], [7, "Red clover"],
        [7, "Common knapweed"], [7, "Common fleabane"], [7, "Barley"], [7, "Lop-grass"],
        [7, "Black bent"], [7, "Creeping cinquefoil"], [7, "Tall fescue"], [7, "Oat"], [7, "Maize"],
        [7, "Couch grass"], [7, "Cut-leaved cranesbill"], [7, "Hoary willow-herb"], [7, "Cabbage"],
        [8, "Fat hen"], [8, "Swine-cress"], [8, "Dove's-foot cranesbill"], [8, "Scentless mayweed"],
        [8, "Wheat"], [8, "Scented mayweed"], [8, "Field bindweed"], [8, "Field madder"],
        [8, "Field pansy"], [8, "Prickly ox-tongue"], [8, "Common field speedwell"], [8, "Hedge mustard"],
        [8, "Charlock"], [8, "Bryum"], [8, "Black-grass"], [8, "Potato"], [8, "Black bindweed"],
        [8, "Common poppy"], [8, "Common orache"], [8, "Fool's parsley"], [8, "Sea beet"],
    ];

    function injectStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = `
            .shdw { font-family: inherit; }
            .shdw select, .shdw input[type=text] {
                width: 100%; box-sizing: border-box; padding: 7px 8px; border: 1px solid #ced4da;
                border-radius: 4px; font-size: 0.88rem; font-family: inherit; background: white;
            }
            .shdw-fieldrow { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 0; }
            .shdw-field { flex: 1; min-width: 160px; }
            .shdw-step { margin-bottom: 14px; }
            .shdw-step:last-child { margin-bottom: 0; }
            .shdw-step-label { font-weight: 600; font-size: 0.82rem; color: #2d6a4f; margin-bottom: 4px; display: block; }
            .shdw-toggle-label { font-size: 0.85rem; display: flex; align-items: center; gap: 6px; }
            .shdw-toggle-label input[type=checkbox] { width: auto; }
            .shdw-preview {
                font-family: 'Consolas', monospace; font-size: 1.1rem; font-weight: bold; color: #1b4332;
                background: white; border: 1px solid #b7d9c4; border-radius: 4px; padding: 8px 12px;
                margin-top: 10px; letter-spacing: 0.5px;
            }
            .shdw-help-btn {
                background: none; border: none; color: #2d6a4f; text-decoration: underline;
                font-size: 0.78rem; font-weight: normal; padding: 0; cursor: pointer; margin-left: 8px;
            }
            .shdw-explainer {
                display: none; font-size: 0.8rem; color: #495057; background: #fff8e6; border: 1px solid #f0dca0;
                border-radius: 4px; padding: 10px; margin-bottom: 10px;
            }
            .shdw-acidity-results { font-size: 0.8rem; color: #495057; margin-top: 4px; max-height: 100px; overflow-y: auto; }
            .shdw-acidity-results .shdw-match-row { padding: 3px 0; cursor: pointer; }
            .shdw-acidity-results .shdw-match-row:hover { color: #2d6a4f; font-weight: 600; }
        `;
        document.head.appendChild(style);
    }

    let uidCounter = 0;

    function mount(container, opts) {
        injectStyles();
        opts = opts || {};
        const uid = 'shdw' + (uidCounter++);

        container.innerHTML = `
            <div class="shdw">
                <button type="button" class="shdw-help-btn" id="${uid}-help" style="margin-left:0;">what's SHADe?</button>
                <div class="shdw-explainer" id="${uid}-explainer">
                    SHADe records the exact physical situation the specimen was found in &mdash;
                    its <b>S</b>ubstrate, <b>H</b>umidity, <b>A</b>cidity, and <b>D</b>isturbance history &mdash;
                    as a short code like <code>TsSc-5-6-5</code>. This is genuinely useful research data:
                    it's what lets someone later explore which microhabitats a species actually favours,
                    across every record in the database. Use the tool below to build it step by step &mdash;
                    you don't need to memorise the codes.
                </div>
                <div class="shdw-step">
                    <span class="shdw-step-label">Substrate 1 (required)</span>
                    <div class="shdw-fieldrow">
                        <div class="shdw-field"><select id="${uid}-sub1-major"></select></div>
                        <div class="shdw-field"><select id="${uid}-sub1-minor"></select></div>
                    </div>
                </div>
                <div class="shdw-step">
                    <label class="shdw-toggle-label">
                        <input type="checkbox" id="${uid}-sub2-toggle">
                        This was an interface between two substrates - add a second one
                    </label>
                    <div class="shdw-fieldrow" id="${uid}-sub2-row" style="margin-top:6px; display:none;">
                        <div class="shdw-field"><select id="${uid}-sub2-major"></select></div>
                        <div class="shdw-field"><select id="${uid}-sub2-minor"></select></div>
                    </div>
                </div>
                <div class="shdw-step">
                    <span class="shdw-step-label">Humidity regime</span>
                    <select id="${uid}-humidity"></select>
                </div>
                <div class="shdw-step">
                    <span class="shdw-step-label">Acidity / alkalinity (pH)</span>
                    <div class="shdw-fieldrow">
                        <div class="shdw-field">
                            <input type="text" id="${uid}-acidity-lookup" placeholder="Type a plant name to estimate pH...">
                            <div class="shdw-acidity-results" id="${uid}-acidity-results"></div>
                        </div>
                        <div class="shdw-field" style="max-width:160px;"><select id="${uid}-acidity"></select></div>
                    </div>
                </div>
                <div class="shdw-step">
                    <span class="shdw-step-label">Disturbance history</span>
                    <select id="${uid}-disturbance"></select>
                </div>
                <div class="shdw-preview" id="${uid}-preview">Complete the fields above to build the code...</div>
            </div>
        `;

        const el = (suffix) => container.querySelector(`#${uid}-${suffix}`);
        const sub1Major = el('sub1-major'), sub1Minor = el('sub1-minor');
        const sub2Major = el('sub2-major'), sub2Minor = el('sub2-minor');
        const sub2Toggle = el('sub2-toggle'), sub2Row = el('sub2-row');
        const humidity = el('humidity'), acidity = el('acidity'), disturbance = el('disturbance');
        const acidityLookup = el('acidity-lookup'), acidityResults = el('acidity-results');
        const preview = el('preview');
        const helpBtn = el('help'), explainer = el('explainer');

        function populateSubstrateMajor(selectEl) {
            selectEl.innerHTML = '<option value="">-- Major substrate --</option>';
            for (const [code, group] of Object.entries(SHADE_SUBSTRATES)) {
                selectEl.innerHTML += `<option value="${code}">${code} - ${group.label}</option>`;
            }
            selectEl.innerHTML += `<option value="X">X - Unknown</option>`;
        }
        function populateSubstrateMinor(majorSelectEl, minorSelectEl, preselect) {
            const major = majorSelectEl.value;
            minorSelectEl.innerHTML = '<option value="">-- Subtype --</option>';
            if (major === 'X' || !major) {
                minorSelectEl.innerHTML += `<option value="x">x - Unknown</option>`;
                if (major === 'X') minorSelectEl.value = 'x';
                return;
            }
            const group = SHADE_SUBSTRATES[major];
            if (!group) return;
            for (const [subCode, subLabel] of Object.entries(group.subs)) {
                minorSelectEl.innerHTML += `<option value="${subCode}">${subLabel}</option>`;
            }
            if (preselect) minorSelectEl.value = preselect;
        }
        function populateNumberSelect(selectEl, options) {
            selectEl.innerHTML = '<option value="">-- Select --</option>';
            for (const [value, label] of options) {
                selectEl.innerHTML += `<option value="${value}">${label}</option>`;
            }
        }

        populateSubstrateMajor(sub1Major);
        populateSubstrateMajor(sub2Major);
        populateSubstrateMinor(sub1Major, sub1Minor);
        populateSubstrateMinor(sub2Major, sub2Minor);
        populateNumberSelect(humidity, SHADE_HUMIDITY);
        populateNumberSelect(disturbance, SHADE_DISTURBANCE);
        acidity.innerHTML = '<option value="">-- Select --</option><option value="0">0 - Unknown</option>';
        for (let ph = 3; ph <= 9; ph++) acidity.innerHTML += `<option value="${ph}">pH ${ph}</option>`;

        function getShadeCode() {
            const s1a = sub1Major.value, s1b = sub1Minor.value;
            const useS2 = sub2Toggle.checked;
            const s2a = sub2Major.value, s2b = sub2Minor.value;
            const h = humidity.value, a = acidity.value, d = disturbance.value;
            if (!s1a || !s1b || h === '' || a === '' || d === '') return null;
            const part1 = s1a + s1b;
            let part2;
            if (useS2) {
                if (!s2a || !s2b) return null;
                part2 = s2a + s2b;
            } else {
                part2 = 'Xx';
            }
            return `${part1}${part2}-${h}-${a}-${d}`;
        }

        function fireChange() {
            const code = getShadeCode();
            preview.textContent = code || 'Complete the fields above to build the code...';
            preview.style.color = code ? '#1b4332' : '#adb5bd';
            if (opts.onChange) opts.onChange(code);
        }

        [sub1Major, sub1Minor, sub2Major, sub2Minor, humidity, acidity, disturbance].forEach(elm => {
            elm.addEventListener('change', fireChange);
        });
        sub1Major.addEventListener('change', () => { populateSubstrateMinor(sub1Major, sub1Minor); fireChange(); });
        sub2Major.addEventListener('change', () => { populateSubstrateMinor(sub2Major, sub2Minor); fireChange(); });
        sub2Toggle.addEventListener('change', () => {
            sub2Row.style.display = sub2Toggle.checked ? 'flex' : 'none';
            if (!sub2Toggle.checked) { sub2Major.value = ''; populateSubstrateMinor(sub2Major, sub2Minor); }
            fireChange();
        });
        acidityLookup.addEventListener('input', () => {
            const q = acidityLookup.value.trim().toLowerCase();
            acidityResults.innerHTML = '';
            if (q.length < 2) return;
            const matches = SHADE_PLANT_PH.filter(([ph, name]) => name.toLowerCase().includes(q)).slice(0, 8);
            matches.forEach(([ph, name]) => {
                const row = document.createElement('div');
                row.className = 'shdw-match-row';
                row.textContent = `${name} -> pH ${ph}`;
                row.addEventListener('click', () => {
                    acidity.value = ph;
                    acidityLookup.value = '';
                    acidityResults.innerHTML = '';
                    fireChange();
                });
                acidityResults.appendChild(row);
            });
        });
        helpBtn.addEventListener('click', () => {
            explainer.style.display = explainer.style.display === 'none' ? 'block' : 'none';
        });

        function setCode(code) {
            // Defensive parse: <sub1major><sub1minor><sub2major><sub2minor>-<humidity>-<acidity>-<disturbance>
            // Anything not matching that exact shape just leaves the
            // builder blank - the raw text elsewhere is never touched
            // by this widget, so nothing is lost either way.
            if (!code || typeof code !== 'string') { fireChange(); return; }
            const m = code.match(/^([A-Za-z])([A-Za-z])([A-Za-z])([A-Za-z])-(\d)-(\d)-(\d)$/);
            if (!m) { fireChange(); return; }
            const [, s1a, s1b, s2a, s2b, h, a, d] = m;
            if (SHADE_SUBSTRATES[s1a]) {
                sub1Major.value = s1a;
                populateSubstrateMinor(sub1Major, sub1Minor, s1b);
            }
            if (s2a === 'X' && s2b === 'x') {
                sub2Toggle.checked = false;
                sub2Row.style.display = 'none';
            } else if (SHADE_SUBSTRATES[s2a]) {
                sub2Toggle.checked = true;
                sub2Row.style.display = 'flex';
                sub2Major.value = s2a;
                populateSubstrateMinor(sub2Major, sub2Minor, s2b);
            }
            humidity.value = h;
            acidity.value = a;
            disturbance.value = d;
            fireChange();
        }

        function reset() {
            sub1Major.value = '';
            populateSubstrateMinor(sub1Major, sub1Minor);
            sub2Toggle.checked = false;
            sub2Row.style.display = 'none';
            sub2Major.value = '';
            populateSubstrateMinor(sub2Major, sub2Minor);
            humidity.value = '';
            acidity.value = '';
            disturbance.value = '';
            acidityLookup.value = '';
            acidityResults.innerHTML = '';
            fireChange();
        }

        if (opts.initialCode) setCode(opts.initialCode);
        else fireChange();

        return { setCode, getCode: getShadeCode, reset };
    }

    global.ShadeWidget = { mount };
})(window);

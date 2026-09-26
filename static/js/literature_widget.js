/*
 * literature_widget.js
 * -----------------------------------------------------------------
 * Shared, embeddable "find or add a literature reference" widget.
 * Designed to be dropped into any form that needs to attach a
 * literature reference: taxonomy editor, sample submission, taxon
 * literature keys, etc. Written once here so every form behaves
 * identically and gets fixes/improvements at the same time.
 *
 * Renders its own fuzzy-search box + results dropdown, plus a
 * collapsible "add a new reference" mini-form covering every column
 * on the literature table, with a Journal / Book / Other switch that
 * shows only the fields relevant to that kind of source. All markup
 * is scoped under litw- prefixed classes with injected <style>, so
 * it renders consistently regardless of the host page's own CSS and
 * never collides with it.
 *
 * Usage:
 *   const handle = LiteratureWidget.mount(containerElement, {
 *       placeholder: 'Search author, title, year...',
 *       onSelected: (lit) => { ... }  // lit = {litID, formatted_ref} or null when cleared
 *   });
 *   handle.clear();  // resets the widget back to its empty state
 *
 * Depends on two existing API endpoints:
 *   GET  /api/v1/literature/search?q=...&limit=...
 *   POST /api/v1/literature   (creates a new literature entry)
 */
(function (global) {
    const STYLE_ID = 'litw-styles';

    function injectStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = `
            .litw { font-family: inherit; }
            .litw-wrapper { position: relative; }
            .litw input[type=text] {
                width: 100%; box-sizing: border-box; padding: 8px 9px; border: 1px solid #ced4da;
                border-radius: 4px; font-size: 0.9rem; font-family: inherit;
            }
            .litw-dropdown {
                position: absolute; top: 100%; left: 0; right: 0; background: #fff;
                border: 1px solid #ced4da; border-top: none; max-height: 320px; overflow-y: auto;
                z-index: 200; display: none; box-shadow: 0 4px 8px rgba(0,0,0,0.2);
            }
            .litw-dropdown.visible { display: block; }
            .litw-row { padding: 8px 10px; cursor: pointer; border-bottom: 1px solid #f1f3f5; font-size: 0.86rem; }
            .litw-row:hover { background: #e9ecef; }
            .litw-selected { font-size: 0.85rem; padding: 6px 0; color: #212529; }
            .litw-selected .litw-placeholder { color: #adb5bd; font-style: italic; }
            .litw-selected .litw-clear {
                background: none; border: none; color: #c1666b; font-size: 0.78rem; cursor: pointer;
                padding: 0 0 0 8px; text-decoration: underline;
            }
            .litw-toggle {
                background: none; border: 1px solid #2d6a4f; color: #2d6a4f; padding: 5px 10px;
                border-radius: 4px; font-size: 0.78rem; cursor: pointer; margin-top: 8px;
            }
            .litw-toggle:hover { background: #e9f5ee; }
            .litw-addform {
                display: none; border: 1px dashed #ced4da; border-radius: 6px; padding: 12px;
                margin-top: 10px; background: #fafbfa;
            }
            .litw-addform.visible { display: block; }
            .litw-type-switch { display: flex; gap: 8px; margin-bottom: 10px; }
            .litw-type-switch button {
                flex: 1; padding: 6px; border: 1px solid #ced4da; background: white; color: #495057;
                border-radius: 4px; cursor: pointer; font-size: 0.8rem;
            }
            .litw-type-switch button.active { background: #2d6a4f; color: white; border-color: #2d6a4f; }
            .litw-fieldrow { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }
            .litw-field { flex: 1; min-width: 150px; display: flex; flex-direction: column; gap: 3px; }
            .litw-field.full { flex-basis: 100%; }
            .litw-field label { font-size: 0.75rem; font-weight: 600; color: #2d6a4f; }
            .litw-savebtn {
                background: #2d6a4f; color: white; border: none; padding: 7px 14px; border-radius: 4px;
                cursor: pointer; font-weight: bold; font-size: 0.82rem;
            }
            .litw-savebtn:hover { background: #1b4332; }
            .litw-status { font-size: 0.8rem; margin-left: 8px; }
            .litw-status.success { color: #1b4332; font-weight: 600; }
            .litw-status.error { color: #842029; }
        `;
        document.head.appendChild(style);
    }

    let uidCounter = 0;
    const PLACEHOLDER_HTML = '<span class="litw-placeholder">No reference selected</span>';

    function mount(container, opts) {
        injectStyles();
        opts = opts || {};
        const uid = 'litw' + (uidCounter++);
        const placeholder = opts.placeholder || 'Search author, title, year...';

        container.innerHTML = `
            <div class="litw">
                <div class="litw-wrapper">
                    <input type="text" id="${uid}-search" placeholder="${placeholder}" autocomplete="off">
                    <div id="${uid}-dropdown" class="litw-dropdown"></div>
                </div>
                <div id="${uid}-selected" class="litw-selected">${PLACEHOLDER_HTML}</div>
                <button type="button" class="litw-toggle" id="${uid}-addtoggle">+ Can't find it? Add a new reference</button>
                <div class="litw-addform" id="${uid}-addform">
                    <div class="litw-type-switch" id="${uid}-typeswitch">
                        <button type="button" data-type="journal" class="active">Journal article</button>
                        <button type="button" data-type="book">Book / report</button>
                        <button type="button" data-type="other">Other</button>
                    </div>
                    <div class="litw-fieldrow">
                        <div class="litw-field"><label>Author(s)</label><input type="text" id="${uid}-author"></div>
                        <div class="litw-field"><label>Editor(s)</label><input type="text" id="${uid}-editor"></div>
                        <div class="litw-field"><label>Year</label><input type="text" id="${uid}-year"></div>
                    </div>
                    <div class="litw-fieldrow">
                        <div class="litw-field full"><label id="${uid}-titlelabel">Article title</label><input type="text" id="${uid}-articletitle"></div>
                    </div>
                    <div class="litw-fieldrow">
                        <div class="litw-field"><label id="${uid}-pubtitlelabel">Journal title</label><input type="text" id="${uid}-pubtitle"></div>
                        <div class="litw-field" id="${uid}-series-field" style="display:none;"><label>Series</label><input type="text" id="${uid}-series"></div>
                        <div class="litw-field"><label>Volume</label><input type="text" id="${uid}-volume"></div>
                        <div class="litw-field"><label>Issue</label><input type="text" id="${uid}-issue"></div>
                    </div>
                    <div class="litw-fieldrow">
                        <div class="litw-field"><label>Pages</label><input type="text" id="${uid}-pages" placeholder="e.g. 112-118"></div>
                        <div class="litw-field" id="${uid}-totalpages-field" style="display:none;"><label>Total pages</label><input type="text" id="${uid}-totalpages"></div>
                        <div class="litw-field" id="${uid}-publisher-field" style="display:none;"><label>Publisher</label><input type="text" id="${uid}-publisher"></div>
                        <div class="litw-field" id="${uid}-isbn-field" style="display:none;"><label>ISBN / ISSN</label><input type="text" id="${uid}-isbn"></div>
                    </div>
                    <div class="litw-fieldrow">
                        <div class="litw-field"><label>DOI</label><input type="text" id="${uid}-doi"></div>
                        <div class="litw-field full"><label>URL</label><input type="text" id="${uid}-url"></div>
                    </div>
                    <div class="litw-fieldrow">
                        <div class="litw-field full"><label>Notes</label><input type="text" id="${uid}-notes"></div>
                    </div>
                    <button type="button" class="litw-savebtn" id="${uid}-save">Add this reference</button>
                    <span class="litw-status" id="${uid}-status"></span>
                </div>
            </div>
        `;

        const el = (suffix) => container.querySelector(`#${uid}-${suffix}`);
        const searchInput = el('search');
        const dropdown = el('dropdown');
        const selectedEl = el('selected');
        let searchTimer = null;
        let suppressNextSearch = false;
        let currentType = 'journal';

        function selectReference(lit) {
            if (lit) {
                selectedEl.innerHTML = `<i>${lit.formatted_ref}</i> <button type="button" class="litw-clear">clear</button>`;
                selectedEl.querySelector('.litw-clear').addEventListener('click', () => {
                    selectedEl.innerHTML = PLACEHOLDER_HTML;
                    searchInput.value = '';
                    if (opts.onSelected) opts.onSelected(null);
                });
            } else {
                selectedEl.innerHTML = PLACEHOLDER_HTML;
            }
            if (opts.onSelected) opts.onSelected(lit);
        }

        searchInput.addEventListener('input', () => {
            if (suppressNextSearch) { suppressNextSearch = false; return; }
            clearTimeout(searchTimer);
            const q = searchInput.value.trim();
            if (q.length < 2) {
                dropdown.classList.remove('visible');
                dropdown.innerHTML = '';
                return;
            }
            searchTimer = setTimeout(async () => {
                try {
                    const res = await fetch(`/api/v1/literature/search?q=${encodeURIComponent(q)}&limit=15`);
                    const data = await res.json();
                    dropdown.innerHTML = '';
                    if (!data.results || data.results.length === 0) {
                        dropdown.innerHTML = '<div class="litw-row">No matches</div>';
                    } else {
                        data.results.forEach(r => {
                            const row = document.createElement('div');
                            row.className = 'litw-row';
                            row.textContent = r.formatted_ref;
                            row.addEventListener('click', () => {
                                dropdown.classList.remove('visible');
                                dropdown.innerHTML = '';
                                suppressNextSearch = true;
                                searchInput.value = r.formatted_ref;
                                selectReference({ litID: r.lit_id, formatted_ref: r.formatted_ref });
                            });
                            dropdown.appendChild(row);
                        });
                    }
                    dropdown.classList.add('visible');
                } catch (err) {
                    dropdown.classList.remove('visible');
                }
            }, 300);
        });

        document.addEventListener('click', (e) => {
            if (!searchInput.contains(e.target) && !dropdown.contains(e.target)) {
                dropdown.classList.remove('visible');
            }
        });

        // ---- add-new-reference mini form ----
        const addToggle = el('addtoggle');
        const addForm = el('addform');
        addToggle.addEventListener('click', () => addForm.classList.toggle('visible'));

        const typeButtons = el('typeswitch').querySelectorAll('button');
        typeButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                typeButtons.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentType = btn.dataset.type;
                applyTypeFields();
            });
        });

        function applyTypeFields() {
            const isJournal = currentType === 'journal';
            el('titlelabel').textContent = isJournal ? 'Article title' : (currentType === 'book' ? 'Chapter title (if applicable)' : 'Title');
            el('pubtitlelabel').textContent = isJournal ? 'Journal title' : (currentType === 'book' ? 'Book / report title' : 'Publication / source');
            const showExtra = !isJournal;
            el('series-field').style.display = showExtra ? 'flex' : 'none';
            el('totalpages-field').style.display = showExtra ? 'flex' : 'none';
            el('publisher-field').style.display = showExtra ? 'flex' : 'none';
            el('isbn-field').style.display = showExtra ? 'flex' : 'none';
        }
        applyTypeFields();

        function resetAddForm() {
            ['author', 'editor', 'year', 'articletitle', 'pubtitle', 'series', 'volume', 'issue',
             'pages', 'totalpages', 'publisher', 'isbn', 'doi', 'url', 'notes'].forEach(f => { el(f).value = ''; });
            typeButtons.forEach(b => b.classList.remove('active'));
            container.querySelector(`#${uid}-typeswitch button[data-type="journal"]`).classList.add('active');
            currentType = 'journal';
            applyTypeFields();
            addForm.classList.remove('visible');
            el('status').textContent = '';
            el('status').className = 'litw-status';
        }

        el('save').addEventListener('click', async () => {
            const statusEl = el('status');
            const payload = {
                authorName: el('author').value || null,
                editorName: el('editor').value || null,
                yearPublished: el('year').value || null,
                articleTitle: el('articletitle').value || null,
                publicationTitle: el('pubtitle').value || null,
                publicationSeries: el('series').value || null,
                publicationVolume: el('volume').value || null,
                publicationIssue: el('issue').value || null,
                publicationTotalpages: el('totalpages').value || null,
                publicationPages: el('pages').value || null,
                publishedBy: el('publisher').value || null,
                publicationISBNorISSN: el('isbn').value || null,
                publicationDOI: el('doi').value || null,
                sourceURL: el('url').value || null,
                litNotes: el('notes').value || null
            };
            if (!payload.authorName && !payload.articleTitle && !payload.publicationTitle) {
                statusEl.textContent = 'Enter at least an author, title, or publication.';
                statusEl.className = 'litw-status error';
                return;
            }
            statusEl.textContent = 'Adding...';
            statusEl.className = 'litw-status';
            try {
                const res = await fetch('/api/v1/literature', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (!res.ok) {
                    statusEl.textContent = data.detail || 'Could not add reference.';
                    statusEl.className = 'litw-status error';
                    return;
                }
                const formattedRef = [payload.authorName, payload.yearPublished, payload.articleTitle || payload.publicationTitle]
                    .filter(Boolean).join(', ');
                resetAddForm();
                searchInput.value = formattedRef;
                selectReference({ litID: data.litID, formatted_ref: formattedRef });
            } catch (err) {
                statusEl.textContent = 'Failed: ' + err;
                statusEl.className = 'litw-status error';
            }
        });

        return {
            clear: () => {
                searchInput.value = '';
                dropdown.classList.remove('visible');
                dropdown.innerHTML = '';
                selectedEl.innerHTML = PLACEHOLDER_HTML;
                resetAddForm();
            }
        };
    }

    global.LiteratureWidget = { mount };
})(window);

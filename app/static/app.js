const $ = selector => document.querySelector(selector);
const state = { path: null, history: [], rows: [], selected: null, mode: 'list', graph: { zoom: 1, x: 0, y: 0, run: 0, rootPath: null, paused: false } };
const icons = { document: '▤', spreadsheet: '▦', dataset: '▦', image: '◉' };

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = response.headers.get('content-type')?.includes('json') ? await response.json() : null;
  if (!response.ok) throw new Error(data?.error || `Erro ${response.status}`);
  return data;
}
const post = (path, data) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[char]));
function bytes(value) { if (!value) return '—'; const units = ['B', 'KB', 'MB', 'GB']; let i = 0; while (value >= 1024 && i < 3) { value /= 1024; i++; } return `${value.toFixed(i ? 1 : 0)} ${units[i]}`; }
function toast(message) { const node = $('#toast'); node.textContent = message; node.classList.remove('hidden'); setTimeout(() => node.classList.add('hidden'), 2800); }
function setPreviewCollapsed(collapsed) { document.body.classList.toggle('preview-collapsed', collapsed); localStorage.setItem('file-index.preview-collapsed', collapsed ? '1' : '0'); document.querySelectorAll('.preview-toggle').forEach(button => button.textContent = collapsed ? '◨ Mostrar preview' : '◧ Ocultar preview'); }

function setNav(name) {
  document.querySelectorAll('[data-nav]').forEach(button => button.classList.toggle('active', button.dataset.nav === name));
  $('#explorerView').classList.toggle('hidden', ['graph', 'collections'].includes(name));
  $('#graphView').classList.toggle('hidden', name !== 'graph');
  $('#collectionsView').classList.toggle('hidden', name !== 'collections');
}
function heading(title, subtitle) { $('#viewHeading').innerHTML = `<h1>${esc(title)}</h1><p>${esc(subtitle)}</p>`; }
function breadcrumbs(path) { return path ? path.replaceAll('\\', ' / ') : 'Explorar'; }

function row(item, folder = false) {
  const node = document.createElement('div'); node.className = 'file-row'; node.tabIndex = 0;
  if (folder) {
    node.innerHTML = `<div class="file-name"><span class="file-icon">▰</span>${esc(item.name)}</div><div class="file-kind">Pasta</div><div class="file-path">${item.files || 0} itens</div><div class="file-size">${bytes(item.bytes)}</div>`;
    node.onclick = () => openFolder(item.path);
  } else {
    node.innerHTML = `<div class="file-name"><span class="file-icon">${icons[item.kind] || '·'}</span>${esc(item.name)}</div><div class="file-kind">${esc(item.kind || 'file')}</div><div class="file-path">${esc(item.path)}</div><div class="file-size">${bytes(item.size)}</div>`;
    node.onclick = () => showDetail(item.id, node); node.ondblclick = () => openFile(item.id);
  }
  node.onkeydown = event => { if (event.key === 'Enter') node.click(); };
  return node;
}
function renderRows(files, folders = []) {
  state.rows = files; const list = $('#fileList'); list.className = `file-list ${state.mode === 'grid' ? 'grid-mode' : ''}`;
  list.replaceChildren(...folders.map(item => row(item, true)), ...files.map(item => row(item)));
  if (!list.childElementCount) list.innerHTML = '<p class="meta">Nenhum item nesta vista.</p>';
}
async function loadRoots() {
  const roots = await api('/api/folders'); const box = $('#rootFolders'); box.replaceChildren(...roots.map(root => {
    const button = document.createElement('button'); button.className = 'root-folder'; button.textContent = `▰ ${root.name}`; button.title = root.path; button.onclick = () => openFolder(root.path); return button;
  }));
}
async function home() { state.path = null; state.history = []; setNav('home'); $('#breadcrumbs').textContent = 'Explorar'; heading('Explorar', 'Ficheiros indexados recentemente.'); renderRows(await api('/api/recent')); }
async function recent() { state.path = null; setNav('recent'); $('#breadcrumbs').textContent = 'Recentes'; heading('Recentes', 'Itens indexados ou atualizados recentemente.'); renderRows(await api('/api/recent')); }
async function openFolder(path, push = true) {
  if (push && state.path && state.path !== path) state.history.push(state.path); state.path = path; setNav('home');
  const data = await api(`/api/folder?path=${encodeURIComponent(path)}`); $('#breadcrumbs').textContent = breadcrumbs(path);
  heading(path.split(/[\\/]/).filter(Boolean).pop(), 'Navegação local — os originais permanecem no lugar.'); renderRows(data.files, data.folders);
}
function back() { const previous = state.history.pop(); return previous ? openFolder(previous, false) : home(); }
function up() { if (!state.path) return home(); const path = state.path.replace(/[\\/]+$/, ''); const separator = path.includes('\\') ? '\\' : '/'; const parent = path.slice(0, path.lastIndexOf(separator)); return parent ? openFolder(parent) : home(); }
async function search() {
  const text = $('#searchInput').value.trim(); if (!text) return home(); state.path = null; setNav('home'); $('#breadcrumbs').textContent = 'Pesquisa';
  heading(`Resultados para “${text}”`, 'Nome, caminho, conteúdo extraído e colunas.'); renderRows(await api(`/api/search?q=${encodeURIComponent(text)}&category=${encodeURIComponent($('#typeFilter').value)}`));
}

function section(title) { const node = document.createElement('section'); node.className = 'preview-section'; node.innerHTML = `<h3>${esc(title)}</h3>`; return node; }
async function showDetail(id, selectedRow) {
  document.querySelectorAll('.file-row.selected').forEach(node => node.classList.remove('selected')); selectedRow?.classList.add('selected'); state.selected = id;
  const data = await api(`/api/details?id=${encodeURIComponent(id)}`), file = data.file, ext = (file.extension || '').toLowerCase(), pane = $('#previewPane'); pane.innerHTML = '';
  const header = document.createElement('div'); header.className = 'preview-header';
  header.innerHTML = `<h2>${esc(file.filename)}</h2><div class="meta">${esc(file.file_category)} · ${bytes(file.size_bytes)}<br>${esc(file.path)}</div><div class="actions"><button data-a="open">Abrir</button><button data-a="reveal">Mostrar no Explorer</button><button data-a="copy">Copiar caminho</button><button data-a="tag">＋ Tag</button><button data-a="relation">＋ Relação</button><button data-a="collection">＋ Coleção</button></div>`;
  pane.append(header); header.querySelector('[data-a=open]').onclick = () => openFile(id); header.querySelector('[data-a=reveal]').onclick = () => api(`/api/reveal?id=${encodeURIComponent(id)}`); header.querySelector('[data-a=copy]').onclick = async () => { await navigator.clipboard.writeText(file.path); toast('Caminho copiado.'); };
  header.querySelector('[data-a=tag]').onclick = () => addTag(id); header.querySelector('[data-a=relation]').onclick = () => addRelation(id); header.querySelector('[data-a=collection]').onclick = () => addToCollection(id);
  if (['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'].includes(ext)) { const block = section('Imagem'); block.innerHTML += `<img class="preview-image" src="/api/image?id=${encodeURIComponent(id)}">`; pane.append(block); }
  else if (ext === '.pdf') { const block = section(`PDF · ${file.page_count || data.pages.length || '?'} páginas`), image = document.createElement('img'); image.className = 'pdf-page'; let page = 1; const controls = document.createElement('div'); controls.className = 'actions'; controls.innerHTML = '<button>←</button><span class="meta"></span><button>→</button>'; const render = () => { image.src = `/api/pdf-page?id=${encodeURIComponent(id)}&page=${page}`; controls.children[1].textContent = `Página ${page}`; }; controls.children[0].onclick = () => { page = Math.max(1, page - 1); render(); }; controls.children[2].onclick = () => { page = Math.min(file.page_count || page + 1, page + 1); render(); }; block.append(controls, image); render(); pane.append(block); }
  else if (['.xlsx', '.xls', '.csv'].includes(ext)) pane.append(datasetPreview(data, id));
  else { const block = section(ext === '.docx' ? 'Word' : 'Conteúdo'), text = document.createElement('div'); text.className = 'document-text'; text.textContent = data.pages.map(page => page.text).join('\n\n') || file.text_content || 'Preview indisponível.'; block.append(text); pane.append(block); }
  const organisation = section('Organização'); organisation.innerHTML += `<div class="chips">${data.tags.map(tag => `<span class="chip">#${esc(tag)}</span>`).join('') || '<span class="meta">Sem tags</span>'}</div><div class="chips" style="margin-top:9px">${data.relations.map(rel => `<span class="chip">${esc(rel.type)} → ${esc(rel.label)}</span>`).join('') || '<span class="meta">Sem relações</span>'}</div>`; pane.append(organisation);
}
function datasetPreview(data, id) {
  const block = section('Dados'), tabs = document.createElement('div'), filter = document.createElement('input'), table = document.createElement('div'); tabs.className = 'dataset-tabs'; filter.placeholder = 'Filtrar valores…'; let active = data.datasets[0]?.sheet || 'Dados';
  data.datasets.forEach(dataset => { const button = document.createElement('button'); button.textContent = dataset.sheet; button.onclick = () => { active = dataset.sheet; load(); }; tabs.append(button); });
  async function load() { const result = await api(`/api/dataset?id=${encodeURIComponent(id)}&sheet=${encodeURIComponent(active)}&q=${encodeURIComponent(filter.value)}`); table.innerHTML = `<div class="dataset-table-wrap"><table class="dataset-table"><thead><tr>${result.columns.map(column => `<th>${esc(column)}</th>`).join('')}</tr></thead><tbody>${result.rows.map(values => `<tr>${values.map(value => `<td>${esc(value)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`; }
  filter.onchange = load; block.append(tabs, filter, table); load(); return block;
}
function openFile(id) { api(`/api/open?id=${encodeURIComponent(id)}`).catch(error => toast(error.message)); }
async function addTag(id) { const name = prompt('Nova tag:'); if (!name?.trim()) return; await post('/api/tags', { file_id: id, name }); showDetail(id); }
async function addRelation(id) { const label = prompt('Relacionar com:'); if (!label?.trim()) return; const target_type = prompt('Tipo (poc, contrato, pessoa, empresa, local, outro):', 'outro') || 'outro'; await post('/api/relations', { file_id: id, label, target_type, relation_type: 'related_to' }); showDetail(id); }
async function addToCollection(id) { const name = prompt('Nome da coleção:'); if (!name?.trim()) return; const collection = await post('/api/collections', { name }); await post('/api/collections/items', { collection_id: collection.id, file_id: id }); toast('Adicionado à coleção.'); }

async function collections() { setNav('collections'); const box = $('#collectionsList'), data = await api('/api/collections'); box.replaceChildren(...data.map(collection => { const card = document.createElement('article'); card.className = 'collection-card'; card.innerHTML = `<h2>${esc(collection.name)}</h2><p class="meta">${esc(collection.description || 'Sem descrição')} · ${collection.items.length} item(ns)</p><div class="chips">${collection.items.map(item => `<button class="chip">${esc(item.label)}</button>`).join('') || '<span class="meta">Vazia</span>'}</div>`; card.querySelectorAll('button').forEach((button, index) => button.onclick = () => showDetail(collection.items[index].id)); return card; })); if (!data.length) box.innerHTML = '<p class="meta">Crie uma coleção para agrupar ficheiros sem tocar nas pastas originais.</p>'; }
async function createCollection() { const name = prompt('Nome da coleção:'); if (name?.trim()) { await post('/api/collections', { name }); collections(); } }

async function startIndex() { const path = $('#indexPath').value.trim(); if (!path) return; await post('/api/index', { path }); $('#indexDialog').close(); poll(); }
async function poll() { const data = await api('/api/progress'); $('#statusLine').textContent = data.active ? `Indexando ${data.total ? Math.round(data.current / data.total * 100) : 0}% · ${data.name}` : data.result || $('#statusLine').textContent; if (data.active) setTimeout(poll, 350); else loadRoots(); }
async function settings() { const status = await api('/api/status'), data = status.settings; $('#settingsDirectories').value = data.directories.join('\n'); $('#settingsIgnored').value = data.ignored_patterns.join('\n'); $('#settingsWatch').checked = data.watch; $('#settingsDialog').showModal(); }
async function saveSettings() { await post('/api/config', { directories: $('#settingsDirectories').value.split('\n').filter(Boolean), ignored_patterns: $('#settingsIgnored').value.split('\n').filter(Boolean), watch: $('#settingsWatch').checked }); toast('Configuração guardada.'); }

function graphTransform() { const g = state.graph; if (g.layer) g.layer.style.transform = `translate(${g.x}px,${g.y}px) scale(${g.zoom})`; }
function zoomGraphAt(canvas, x, y, factor) { const g = state.graph, next = Math.max(.35, Math.min(3, g.zoom * factor)), ratio = next / g.zoom; g.x = x - (x - g.x) * ratio; g.y = y - (y - g.y) * ratio; g.zoom = next; graphTransform(); }
async function orbitGraph(path = null, focus = null) {
  setNav('graph'); const hideFiles = $('#graphFiles').checked, query = new URLSearchParams({ files: hideFiles ? '0' : '1' }); if (path) query.set('path', path); if (hideFiles && focus) query.set('focus', focus);
  renderNetwork(await api(`/api/graph?${query}`), { kind: 'orbit', path, focus });
}
async function excelConstellation() { setNav('graph'); renderNetwork(await api('/api/excel-graph'), { kind: 'excel' }); }
function renderNetwork(data, options) {
  const canvas = $('#graphCanvas'), g = state.graph, run = ++g.run, width = canvas.clientWidth, height = canvas.clientHeight; canvas.innerHTML = ''; g.zoom = 1; g.x = g.y = 0;
  $('#orbitTitle').textContent = options.kind === 'excel' ? `⌗ Constelação Excel${data.isolated_files ? ` · ${data.isolated_files} sem correspondência` : ''}` : options.focus ? '◎ Órbitas · ficheiros revelados' : '◎ Órbitas';
  const layer = document.createElement('div'); layer.className = 'graph-layer'; canvas.append(layer); g.layer = layer;
  const hint = document.createElement('div'); hint.id = 'orbitHint'; hint.className = 'orbit-hint'; hint.textContent = options.kind === 'excel' ? 'Linhas unem Excels com colunas em comum · clique para pré-visualizar' : $('#graphFiles').checked ? 'Clique numa pasta para revelar apenas os ficheiros dela' : 'Clique numa pasta para navegar · clique num ficheiro para pré-visualizar'; canvas.append(hint);
  if (!data.nodes.length) { canvas.innerHTML = '<p class="meta" style="padding:24px">Nenhuma correspondência disponível nesta vista.</p>'; return; }
  const nodes = data.nodes.map(node => ({ ...node, x: 0, y: 0, vx: 0, vy: 0, fixed: false })), map = new Map(nodes.map(node => [node.id, node])), children = new Map();
  data.edges.forEach(edge => { if (!children.has(edge.source)) children.set(edge.source, []); children.get(edge.source).push(edge.target); }); const center = nodes.find(node => node.center || node.type === 'workspace') || nodes[0];
  if (options.kind === 'orbit') {
    g.rootPath = center.path || options.path; center.x = width / 2; center.y = height / 2; center.fixed = true;
    const place = (parent, depth, start, span) => (children.get(parent.id) || []).forEach((id, index, ids) => { const node = map.get(id), angle = start + span * (index + .5) / ids.length, radius = node.type === 'file' ? 82 + Math.floor(index / 8) * 14 : depth ? 145 : 235; node.x = node.homeX = parent.x + Math.cos(angle) * radius; node.y = node.homeY = parent.y + Math.sin(angle) * radius; if (node.type !== 'file') place(node, depth + 1, angle - .8, 1.6); });
    place(center, 0, -Math.PI, Math.PI * 2);
  } else nodes.forEach((node, index) => { const angle = Math.PI * 2 * index / nodes.length, radius = Math.min(width, height) * .28; node.x = width / 2 + Math.cos(angle) * radius; node.y = height / 2 + Math.sin(angle) * radius; });
  const elements = new Map(); let selectedElement = null; nodes.forEach(node => {
    const el = document.createElement('div'); el.className = `graph-node ${node.type}`; el.textContent = node.type === 'file' ? node.label : `${node.type === 'excel' ? '▦' : '▰'} ${node.label}`; el.title = node.label; layer.append(el); let drag = false;
    el.onpointerdown = event => { drag = true; el.setPointerCapture?.(event.pointerId); event.stopPropagation(); }; el.onpointermove = event => { if (!drag) return; const rect = canvas.getBoundingClientRect(); node.x = (event.clientX - rect.left - g.x) / g.zoom; node.y = (event.clientY - rect.top - g.y) / g.zoom; node.vx = node.vy = 0; node.fixed = true; }; el.onpointerup = () => drag = false;
    el.onclick = event => { event.stopPropagation(); selectedElement?.classList.remove('selected'); selectedElement = el; el.classList.add('selected'); if (options.kind === 'orbit' && node.type === 'folder') { hint.textContent = $('#graphFiles').checked ? `A revelar ficheiros de ${node.label}…` : `A navegar para ${node.label}…`; if ($('#graphFiles').checked) orbitGraph(g.rootPath, node.path); else if (node !== center) orbitGraph(node.path); } else if (node.file_id) { hint.textContent = `${node.label} · duplo clique para abrir no sistema`; showDetail(node.file_id); } }; el.ondblclick = () => node.file_id && openFile(node.file_id); elements.set(node.id, el);
  });
  const links = data.edges.map(edge => { const el = document.createElement('i'); el.className = `graph-edge ${edge.kind === 'shared_columns' ? 'shared' : map.get(edge.target)?.type === 'folder' ? 'folder' : ''}`; el.title = edge.columns?.join(', ') || ''; layer.append(el); return { edge, el }; });
  let pan = false, px = 0, py = 0; canvas.onpointerdown = event => { if (event.target === canvas || event.target === layer) { pan = true; px = event.clientX; py = event.clientY; canvas.setPointerCapture?.(event.pointerId); } }; canvas.onpointermove = event => { if (!pan) return; g.x += event.clientX - px; g.y += event.clientY - py; px = event.clientX; py = event.clientY; graphTransform(); }; canvas.onpointerup = () => pan = false; canvas.onwheel = event => { event.preventDefault(); const rect = canvas.getBoundingClientRect(); zoomGraphAt(canvas, event.clientX - rect.left, event.clientY - rect.top, event.deltaY < 0 ? 1.12 : .89); }, { passive: false };
  const draw = () => { nodes.forEach(node => { const el = elements.get(node.id); el.style.left = `${node.x}px`; el.style.top = `${node.y}px`; }); links.forEach(({ edge, el }) => { const a = map.get(edge.source), b = map.get(edge.target), dx = b.x - a.x, dy = b.y - a.y; el.style.left = `${a.x}px`; el.style.top = `${a.y}px`; el.style.width = `${Math.hypot(dx, dy)}px`; el.style.transform = `rotate(${Math.atan2(dy, dx)}rad)`; }); };
  const tick = time => { if (run !== g.run) return; if (!g.paused) { for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) { const a = nodes[i], b = nodes[j], dx = a.x - b.x, dy = a.y - b.y, d = Math.max(18, Math.hypot(dx, dy)), force = (a.type === 'file' && b.type === 'file' ? 600 : 1500) / (d * d); if (!a.fixed) { a.vx += dx / d * force; a.vy += dy / d * force; } if (!b.fixed) { b.vx -= dx / d * force; b.vy -= dy / d * force; } } links.forEach(({ edge }) => { const a = map.get(edge.source), b = map.get(edge.target), dx = b.x - a.x, dy = b.y - a.y, d = Math.max(1, Math.hypot(dx, dy)), ideal = edge.kind === 'shared_columns' ? 190 : b.type === 'file' ? 95 : 165, pull = (d - ideal) * .006; if (!a.fixed) { a.vx += dx / d * pull; a.vy += dy / d * pull; } if (!b.fixed) { b.vx -= dx / d * pull; b.vy -= dy / d * pull; } }); nodes.forEach((node, index) => { if (node.fixed) return; const hx = node.homeX ?? node.x, hy = node.homeY ?? node.y; node.vx += (hx - node.x) * .002 + Math.sin(time * .001 + index) * .01; node.vy += (hy - node.y) * .002 + Math.cos(time * .0012 + index) * .01; node.vx *= .9; node.vy *= .9; node.x += node.vx; node.y += node.vy; }); } draw(); requestAnimationFrame(tick); }; draw(); requestAnimationFrame(tick);
}

function bind() {
  document.querySelectorAll('[data-nav]').forEach(button => button.onclick = () => ({ home, recent, graph: orbitGraph, collections }[button.dataset.nav]())); $('#refreshRoots').onclick = loadRoots; $('#backButton').onclick = back; $('#upButton').onclick = up; $('#searchInput').onkeydown = event => event.key === 'Enter' && search(); $('#typeFilter').onchange = search;
  $('#listMode').onclick = () => { state.mode = 'list'; renderRows(state.rows); }; $('#gridMode').onclick = () => { state.mode = 'grid'; renderRows(state.rows); }; $('#indexButton').onclick = () => $('#indexDialog').showModal(); $('#startIndex').onclick = event => { event.preventDefault(); startIndex(); }; $('#settingsButton').onclick = settings; $('#saveSettings').onclick = event => { event.preventDefault(); saveSettings(); $('#settingsDialog').close(); }; $('#createCollection').onclick = createCollection;
  document.querySelectorAll('.preview-toggle').forEach(button => button.onclick = () => setPreviewCollapsed(!document.body.classList.contains('preview-collapsed'))); $('#graphRoot').onclick = () => orbitGraph(); $('#schemaGraph').onclick = excelConstellation; $('#graphFiles').onchange = () => orbitGraph(state.graph.rootPath); $('#graphZoomIn').onclick = () => { const canvas = $('#graphCanvas'); zoomGraphAt(canvas, canvas.clientWidth / 2, canvas.clientHeight / 2, 1.25); }; $('#graphZoomOut').onclick = () => { const canvas = $('#graphCanvas'); zoomGraphAt(canvas, canvas.clientWidth / 2, canvas.clientHeight / 2, .8); }; $('#graphReset').onclick = () => { state.graph.zoom = 1; state.graph.x = state.graph.y = 0; graphTransform(); }; $('#physicsToggle').onclick = () => { state.graph.paused = !state.graph.paused; $('#physicsToggle').textContent = state.graph.paused ? '▶ Retomar' : '❚❚ Pausar'; };
  document.addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); $('#searchInput').focus(); } if (event.key === 'Escape') { $('#settingsDialog').close(); $('#indexDialog').close(); } });
}
async function start() { bind(); setPreviewCollapsed(localStorage.getItem('file-index.preview-collapsed') === '1'); const status = await api('/api/status'); $('#statusLine').textContent = `V${status.version} · ${status.files} ficheiros`; await loadRoots(); await home(); }
start().catch(error => toast(error.message));

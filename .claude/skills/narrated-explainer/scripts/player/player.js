// Deterministic player: every frame is a pure function of t (seconds). No wall-clock animation, so any frame is
// reproducible and unchanged frames can be skipped by the renderer. Scene kinds are documented in references/scene-kinds.md.
let TL = null, current = null, cache = {};
const $ = (id) => document.getElementById(id);
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const ease = (x) => 1 - Math.pow(1 - clamp(x), 3);
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const setStyle = (el, o) => { for (const k in o) el.style[k] = o[k]; };
const off = (sc) => sc.audioOffset ?? sc.lead;

// Reveal progress for item i of n, spread across the narration window [from,to] (fractions of the audio).
function itemT(sc, local, i, n, from = 0.05, to = 0.85) {
  const at = off(sc) + sc.audioSec * (from + (to - from) * (n <= 1 ? 0 : i / (n - 1)));
  return ease((local - at) / 0.5);
}
const reveal = (el, p) => setStyle(el, { opacity: p, transform: `translateY(${(1 - p) * 24}px)` });
const TONE_ICON = { ok: '✓', bad: '✗', warn: '!', info: '•' };
const norm = (h) => (typeof h === 'string' ? { text: h, tone: 'info' } : { tone: 'info', ...h });
const kv = (it) => (typeof it === 'string' ? { k: '', v: it } : it);

const DEFAULT_COLOUR = [
  { match: '\\b(error|fail(ed|ure)?|denied|refused|fatal|traceback|cannot|not found|no such)\\b', flags: 'i', tone: 'bad' },
  { match: '\\b(warn(ing)?)\\b', flags: 'i', tone: 'warn' },
  { match: '\\b(ok|passed|success(ful)?|done)\\b', flags: 'i', tone: 'ok' },
];

const BUILD = {
  title(sc, st) {
    st.innerHTML = `<div class="center"><div class="lock" id="a">${esc(sc.data?.icon ?? '▶')}</div><h1 id="b">${esc(sc.onScreen[0])}</h1><div class="sub" id="c">${esc(sc.onScreen[1] || '')}</div></div>`;
    return (local) => { reveal($('a'), ease(local / 0.7)); reveal($('b'), ease((local - 0.3) / 0.8)); reveal($('c'), ease((local - 0.9) / 0.8)); };
  },
  disclaimer(sc, st) {
    const [h, ...rest] = sc.onScreen;
    st.innerHTML = `<div class="warnpanel"><h2 id="h">⚠ ${esc(h)}</h2><ul>${rest.map((r, i) => `<li id="r${i}"><span>•</span><span>${esc(r)}</span></li>`).join('')}</ul>
      ${sc.data?.foot ? `<div class="foot" id="f">${esc(sc.data.foot)}</div>` : ''}</div>`;
    return (local) => { reveal($('h'), ease((local - 0.2) / 0.6)); rest.forEach((_, i) => reveal($('r' + i), itemT(sc, local, i, rest.length, 0.25, 0.7))); if ($('f')) reveal($('f'), itemT(sc, local, 0, 1, 0.85, 0.85)); };
  },
  explainer(sc, st) {
    const items = sc.onScreen.map(kv);
    st.innerHTML = `<div class="cards">${items.map((t, i) => `<div class="card" id="k${i}">${t.k ? `<div class="k">${esc(t.k)}</div>` : ''}<div class="v">${esc(t.v)}</div></div>`).join('')}</div>`;
    return (local) => items.forEach((_, i) => reveal($('k' + i), itemT(sc, local, i, items.length, 0.05, 0.8)));
  },
  section(sc, st) {
    st.innerHTML = `<div class="center"><h1 id="a">${esc(sc.onScreen?.[0] || '')}</h1><div class="sub" id="b">${esc(sc.onScreen?.[1] || '')}</div></div>`;
    return (local) => { reveal($('a'), ease(local / 0.6)); reveal($('b'), ease((local - 0.4) / 0.6)); };
  },
  summary(sc, st) {
    const items = sc.onScreen.map((t) => (typeof t === 'string' ? { text: t } : t));
    st.innerHTML = `<div class="checklist"><h2 id="h">${esc(sc.title || 'Summary')}</h2>${items.map((t, i) =>
      `<div class="item ${t.tone === 'warn' ? 'last' : ''}" id="s${i}"><span class="ic">${t.tone === 'warn' ? '!' : '✓'}</span><span>${esc(t.text)}</span></div>`).join('')}</div>`;
    return (local) => { reveal($('h'), ease(local / 0.5)); items.forEach((_, i) => reveal($('s' + i), itemT(sc, local, i, items.length, 0.04, 0.72))); };
  },
  flow(sc, st) {
    const d = sc.data;
    if (d.type === 'branch') {
      st.innerHTML = `<div class="flowwrap"><h2 id="h">${esc(d.title)}</h2><div class="q" id="q">${esc(d.question)}</div>
        <div class="branches"><div class="br" id="y"><div class="bl ok">${esc(d.yes.label)}</div><div class="bt">${esc(d.yes.text)}</div></div>
        <div class="br ${d.no.bad ? 'badnode' : ''}" id="no"><div class="bl bad">${esc(d.no.label)}</div><div class="bt">${esc(d.no.text)}</div></div></div>
        <div class="note" id="nt">${esc(d.note || '')}</div></div>`;
      return (local) => { reveal($('h'), ease(local / 0.5)); reveal($('q'), itemT(sc, local, 0, 1, 0.08, 0.08)); reveal($('y'), itemT(sc, local, 0, 1, 0.3, 0.3)); reveal($('no'), itemT(sc, local, 0, 1, 0.55, 0.55)); reveal($('nt'), itemT(sc, local, 0, 1, 0.8, 0.8)); };
    }
    st.innerHTML = `<div class="flowwrap"><h2 id="h">${esc(d.title)}</h2><div class="chain${d.nodes.length > 6 ? ' dense' : ''}">${d.nodes.map((n, i) =>
      `${i ? `<div class="arrow" id="ar${i}">➜</div>` : ''}<div class="node ${n.bad ? 'badnode' : ''}" id="n${i}"><div class="nl">${esc(n.label)}</div><div class="ns">${esc(n.sub || '')}</div></div>`).join('')}</div></div>`;
    return (local) => { reveal($('h'), ease(local / 0.5)); d.nodes.forEach((_, i) => { reveal($('n' + i), itemT(sc, local, i, d.nodes.length, 0.08, 0.8)); if (i) reveal($('ar' + i), itemT(sc, local, i, d.nodes.length, 0.08, 0.8)); }); };
  },
  filestack(sc, st) {
    const d = sc.data, n = d.stages.length;
    st.innerHTML = `<div class="flowwrap"><h2 id="h">${esc(d.title)}</h2><div id="stages"></div><div class="note" id="fn">${esc(d.footnote || '')}</div></div>`;
    return (local) => {
      reveal($('h'), ease(local / 0.5));
      const f = clamp((local - off(sc)) / sc.audioSec), k = Math.min(n - 1, Math.floor(f * n)), sf = clamp(f * n - k);
      const stg = d.stages[k], key = k + ':' + Math.floor(sf * 10) + ':' + (sf > 0.55);
      if (cache.key !== key) {
        cache.key = key;
        const reading = Math.min(stg.files.length, Math.floor(sf / 0.5 * stg.files.length) + 1);
        $('stages').innerHTML = `<div class="stagelabel">${esc(stg.label)}</div>` + stg.files.map((fl, i) => {
          const won = sf > 0.55 && i === stg.winner, lost = sf > 0.55 && i !== stg.winner, visible = sf < 0.55 ? i < reading : true;
          return `<div class="fcard ${won ? 'win' : ''} ${lost ? 'lose' : ''}" style="opacity:${visible ? 1 : 0}"><span class="fn">${i + 1}. ${esc(fl.name)}</span><span class="fv">${esc(fl.value)}</span><span class="tag">${won ? '✓ ' + esc(d.winLabel || 'wins') : lost ? '✗ ' + esc(d.loseLabel || 'ignored') : ''}</span></div>`;
        }).join('') + `<div class="readarrow">${esc(d.readLabel || '▼ read top to bottom')}</div>`;
      }
    };
  },
  compare(sc, st) {
    const d = sc.data;
    st.innerHTML = `<div class="flowwrap"><table class="cmp"><thead><tr>${d.head.map((h) => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${d.rows.map((r, i) =>
      `<tr id="row${i}">${r.map((c, j) => `<td class="${j === 0 ? 'rl' : ''}">${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
    return (local) => d.rows.forEach((_, i) => reveal($('row' + i), itemT(sc, local, i, d.rows.length, 0.1, 0.55)));
  },
  steps(sc, st) {
    const d = sc.data, flat = [];
    d.columns.forEach((c, ci) => c.items.forEach((it, ii) => flat.push([ci, ii])));
    st.innerHTML = `<div class="flowwrap"><h2 id="h">${esc(d.title)}</h2><div class="cols" style="grid-template-columns:repeat(${d.columns.length},1fr)">${d.columns.map((c, ci) =>
      `<div class="col"><div class="ct">${esc(c.title)}</div><ol>${c.items.map((it, ii) => `<li id="s${ci}_${ii}">${esc(it)}</li>`).join('')}</ol></div>`).join('')}</div></div>`;
    return (local) => { reveal($('h'), ease(local / 0.5)); flat.forEach(([ci, ii], i) => reveal($(`s${ci}_${ii}`), itemT(sc, local, i, flat.length, 0.06, 0.9))); };
  },
  cmdlist(sc, st) {
    const d = sc.data, p = TL.meta.prompt;
    st.innerHTML = `<div class="flowwrap"><h2 id="h">${esc(d.title)}</h2><div class="banner" id="bn">${esc(d.banner || '')}</div>${d.items.map((it, i) =>
      `<div class="cmd" id="c${i}"><div class="cc">${esc(p)}${esc(it.cmd)}</div><div class="cn">${esc(it.note || '')}</div></div>`).join('')}</div>`;
    return (local) => { reveal($('h'), ease(local / 0.5)); reveal($('bn'), ease((local - 0.3) / 0.5)); d.items.forEach((_, i) => reveal($('c' + i), itemT(sc, local, i, d.items.length, 0.1, 0.9))); };
  },
  screenshot(sc, st) {
    const d = sc.data, ann = d.annotations ?? [];
    st.innerHTML = `<div class="shotwrap"><div class="browser"><div class="bbar"><span class="dot" style="background:#ff5f56"></span><span class="dot" style="background:#ffbd2e"></span><span class="dot" style="background:#27c93f"></span>
      <span class="burl">${esc(d.url ?? '')}</span></div><div class="imgbox"><div class="imgwrap"><img id="im" src="${esc(d.imageUrl)}">${ann.map((a, i) =>
      `<div class="abox" id="a${i}" style="left:${a.box[0] * 100}%;top:${a.box[1] * 100}%;width:${a.box[2] * 100}%;height:${a.box[3] * 100}%"></div>`).join('')}</div></div></div>
      <div class="side" id="side">${d.title ? `<div class="stitle">${esc(d.title)}</div>` : ''}${ann.map((a, i) => `<div class="callout ${a.tone ?? 'info'}" id="c${i}"><span class="ic ${a.tone ?? 'info'}">${TONE_ICON[a.tone ?? 'info']}</span><span>${esc(a.label)}</span></div>`).join('')}</div></div>`;
    return (local) => ann.forEach((a, i) => { const p = itemT(sc, local, i, ann.length, 0.15, 0.8); reveal($('c' + i), p); $('a' + i).style.opacity = p; });
  },
  clip(sc, st) {
    // Live footage (nx clips): one pre-extracted frame per output frame, so any frame is reproducible. Times in data are clip
    // seconds, resolved by make-timeline; the speed label comes from the clip's edit and is always on.
    const d = sc.data, fr = d.frames, co = d.callouts ?? [], zm = d.zoom ?? [];
    st.innerHTML = `<div class="shotwrap"><div class="browser"><div class="bbar"><span class="dot" style="background:#ff5f56"></span><span class="dot" style="background:#ffbd2e"></span><span class="dot" style="background:#27c93f"></span>
      <span class="burl" id="burl"></span><span class="speed" id="spd"></span></div><div class="imgbox clipbox"><div class="cam" id="cam"><img id="cv" src="${esc(fr.dir)}/00000.jpg"></div></div></div>
      <div class="side">${d.title ? `<div class="stitle">${esc(d.title)}</div>` : ''}${co.map((a, i) => `<div class="callout ${a.tone ?? 'info'}" id="c${i}"><span class="ic ${a.tone ?? 'info'}">${TONE_ICON[a.tone ?? 'info']}</span><span>${esc(a.label)}</span></div>`).join('')}</div></div>`;
    return (local) => {
      const ct = Math.max(0, local - d.clipStart);
      const n = Math.min(fr.count - 1, Math.floor(ct * fr.fps + 1e-6)), src = `${fr.dir}/${String(n).padStart(5, '0')}.jpg`;
      if (cache.src !== src) { $('cv').src = src; cache.src = src; }
      const cut = d.cuts.some((c) => ct >= c && ct < c + 0.6), sp = d.speed.find((x) => ct >= x.from && ct < x.to);
      $('spd').textContent = local < d.clipStart ? '' : cut ? 'cut' : sp ? sp.text : ct >= d.clipSec ? '■ last frame held' : '';
      $('burl').textContent = [...d.urls].reverse().find((u) => ct >= u.at)?.url ?? d.urls[0].url;
      co.forEach((a, i) => reveal($('c' + i), ease((ct - a.at) / 0.4)));
      // zoom keys: each eases from the previous scale to its own; origin carries over until a key sets a new one
      let scale = 1, origin = '50% 50%';
      for (const z of zm) {
        if (ct < z.at) break;
        const prev = scale; origin = z.origin ?? origin;
        scale = prev + (z.scale - prev) * ease((ct - z.at) / (z.dur ?? 0.8));
      }
      setStyle($('cam'), { transformOrigin: origin, transform: `scale(${scale.toFixed(4)})` });
    };
  },
  terminal(sc, st) {
    const P = TL.meta.prompt;
    st.innerHTML = `<div class="termwrap"><div class="term"><div class="bar"><span class="dot" style="background:#ff5f56"></span><span class="dot" style="background:#ffbd2e"></span><span class="dot" style="background:#27c93f"></span>
      <span style="margin-left:14px">${esc(sc.part)} · ${esc(TL.meta.replayLabel)}</span></div><pre id="pre"><div id="inner"></div></pre></div><div class="side" id="side"></div></div>`;
    const n = sc.steps.length, TYPE = sc.type, hl = sc.highlight.map(norm);
    $('side').innerHTML = hl.map((h, i) => `<div class="callout ${h.tone}" id="h${i}"><span class="ic ${h.tone}">${TONE_ICON[h.tone] ?? '•'}</span><span>${esc(h.text)}</span></div>`).join('');
    const rules = (TL.meta.colour || DEFAULT_COLOUR).map((r) => ({ re: new RegExp(r.match, r.flags ?? ''), tone: r.tone }));
    const colour = (l) => { const r = rules.find((x) => x.re.test(l)); return r ? `<span class="${r.tone}${TL.meta.lineIcons ? ' ic-' + r.tone : ''}">${esc(l)}</span>` : esc(l); };
    const done = (s) => `<span class="p">${esc(P)}</span><span class="c">${esc(s.cmd)}</span>\n` + s.out.map((l) => `<span class="o">${colour(l)}</span>\n`).join('');
    const priorHtml = sc.prior.map(done).join('');
    return (local) => {
      let html = priorHtml;
      sc.steps.forEach((s, i) => {
        const p = sc.plan[i];
        if (local < p.t0) return;
        const k = Math.min(s.cmd.length, Math.floor((local - p.t0) * TYPE));
        html += `<span class="p">${esc(P)}</span><span class="c">${esc(s.cmd.slice(0, k))}</span>`;
        const typing = k < s.cmd.length, running = !typing && local < p.tOut;
        if (typing) html += '<span class="cursor"></span>';
        html += '\n';
        if (running) html += '<span class="o">…</span>\n';
        if (local >= p.tOut) s.out.forEach((l, j) => { if (local >= p.tOut + j * 0.12) html += `<span class="o">${colour(l)}</span>\n`; });
      });
      if (local >= sc.plan[n - 1].tOut + 0.4) html += `<span class="p">${esc(P)}</span><span class="cursor"></span>`;
      if (cache.html !== html) { $('inner').innerHTML = html; cache.html = html; }
      hl.forEach((_, i) => reveal($('h' + i), ease((local - (sc.hlStart + i * sc.hlGap)) / 0.4)));
    };
  },
};

function captionHTML(sc, local) {
  const words = sc.words, o = off(sc);
  if (!words.length || local < o - 0.1 || local > o + sc.audioSec + 0.3) return '';
  let idx = words.findIndex((w) => local < w.end); if (idx < 0) idx = words.length - 1;
  const size = 9, g = Math.floor(idx / size), seg = words.slice(g * size, g * size + size);
  return '<span>' + seg.map((w) => `<span class="w ${local >= w.start && local < w.end ? 'now' : local >= w.end ? 'past' : ''}">${esc(w.text)}</span>`).join(' ') + '</span>';
}

window.setTimeline = (tl) => { TL = tl; current = null; };
// Returns the serialized app HTML so the renderer can skip identical frames.
window.renderAt = (t) => {
  const sc = TL.scenes.find((s) => t >= s.start && t < s.start + s.duration) || TL.scenes[TL.scenes.length - 1];
  const local = t - sc.start;
  if (current !== sc.id) { cache = {}; current = sc.id; window.__draw = BUILD[sc.kind](sc, $('stage')); }
  $('chip').textContent = sc.kind === 'section' ? TL.meta.chip : (sc.part || TL.meta.chip);
  window.__draw(local);
  const fade = Math.min(sc.first ? clamp(local / 0.35) : 1, sc.last ? clamp((sc.duration - local) / 0.35) : 1);
  $('stage').style.opacity = Math.round(fade * 100) / 100; $('caption').style.opacity = Math.round(fade * 100) / 100;
  $('caption').innerHTML = captionHTML(sc, local);
  $('bar').style.width = Math.round(TL.width * t / TL.duration) + 'px';
  return $('app').innerHTML;
};

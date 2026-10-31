// smalldocs: the behaviour of the page. Search, copy buttons, anchors, the table of contents, the theme toggle, listings.
(() => {
  "use strict";
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const offset = ($('meta[name="smalldocs:offset"]') || { content: "./" }).content;
  const store = {
    get: (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* private window */ } },
  };

  // ---- the header's height, for sticky sidebars and anchor scrolling
  const header = $("#quarto-header");
  const setHeader = () => {
    const h = header ? header.offsetHeight : 0;
    document.documentElement.style.setProperty("--sd-header-height", h + "px");
    document.documentElement.style.scrollPaddingTop = h + 16 + "px";
  };
  setHeader();
  if (header && window.ResizeObserver) new ResizeObserver(setHeader).observe(header);

  // ---- light or dark: the theme decides; we read its background for the code colours
  const markDark = () => {
    const bg = getComputedStyle(document.body).backgroundColor.match(/\d+(\.\d+)?/g);
    if (!bg) return;
    const [r, g, b] = bg.map(Number);
    const dark = 0.299 * r + 0.587 * g + 0.114 * b < 128;
    document.documentElement.classList.toggle("quarto-dark", dark);
    $$(".sd-navbar-default").forEach((n) => { n.dataset.bsTheme = dark ? "dark" : "light"; });
  };
  // The head's script has set data-scheme from the stored choice, or else from the mode the browser prefers
  const setScheme = (alt) => {
    if (alt) document.documentElement.dataset.scheme = "alternate"; else delete document.documentElement.dataset.scheme;
    $$("link.quarto-color-scheme").forEach((l) => { l.media = l.classList.contains("quarto-color-alternate") === alt ? "all" : "not all"; });
    setTimeout(markDark, 50);
  };
  window.smalldocsToggleScheme = () => {
    const alt = document.documentElement.dataset.scheme !== "alternate";
    store.set("smalldocs-scheme", alt ? "alternate" : "default");
    setScheme(alt);
  };
  if ($$("link.quarto-color-scheme").length > 1) {
    setScheme(document.documentElement.dataset.scheme === "alternate");
    const prefers = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)");
    if (prefers && prefers.addEventListener) prefers.addEventListener("change", (e) => { if (!store.get("smalldocs-scheme")) setScheme(e.matches); });
  } else markDark();
  window.addEventListener("load", markDark);

  // ---- margin notes: beside their block on a wide screen, after it on a narrow one
  const narrow = window.matchMedia ? window.matchMedia("(max-width: 991.98px)") : null;
  // a note after a heading stays there: it belongs to the heading
  const notes = $$(".column-container").map((n) => [n, n.nextElementSibling]).filter(([n, b]) => b && !/^H[1-6]$/.test((n.previousElementSibling || {}).tagName || ""));
  const placeNotes = () => notes.forEach(([n, b]) => (narrow && narrow.matches ? b.after(n) : b.before(n)));
  if (notes.length && narrow) { placeNotes(); if (narrow.addEventListener) narrow.addEventListener("change", placeNotes); }

  // ---- hide the sidebar or the table of contents while margin or wide content passes under it, as Quarto does
  const wide = $$(".column-margin, .margin-caption, .margin-aside, div.aside, [class*='column-page'], [class*='column-screen'], [class*='column-body-outset']");
  const panels = $$("#quarto-margin-sidebar, #quarto-sidebar");
  if (wide.length && panels.length) {
    const hit = (a, b) => a.width && b.width && a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
    let queued = false;
    const check = () => {
      queued = false;
      panels.forEach((p) => {
        p.classList.remove("sd-overlapped");
        const r = p.getBoundingClientRect();
        p.classList.toggle("sd-overlapped", wide.some((w) => !p.contains(w) && hit(r, w.getBoundingClientRect())));
      });
    };
    const queue = () => { if (!queued) { queued = true; requestAnimationFrame(check); } };
    window.addEventListener("scroll", queue, { passive: true });
    window.addEventListener("resize", queue);
    queue();
  }

  // ---- the sidebar on narrow screens
  const sidebar = $("#quarto-sidebar"), glass = $("#quarto-sidebar-glass");
  const toggleSidebar = (open) => {
    if (!sidebar) return;
    const show = open === undefined ? !sidebar.classList.contains("show") : open;
    sidebar.classList.toggle("show", show);
    if (glass) glass.classList.toggle("show", show);
  };
  $$(".quarto-btn-toggle").forEach((b) => b.addEventListener("click", () => toggleSidebar()));
  if (glass) glass.addEventListener("click", () => toggleSidebar(false));

  // ---- copy buttons
  $$(".code-copy-button").forEach((btn) => btn.addEventListener("click", async () => {
    const code = btn.parentElement.querySelector("pre code");
    if (!code) return;
    try { await navigator.clipboard.writeText(code.innerText); } catch (e) { return; }
    btn.classList.add("code-copy-button-checked");
    btn.title = "Copied!";
    setTimeout(() => { btn.classList.remove("code-copy-button-checked"); btn.title = "Copy to Clipboard"; }, 1500);
  }));

  // ---- anchors on headings
  $$("main .anchored[data-anchor-id]").forEach((h) => {
    if (h.classList.contains("no-anchor") || h.closest(".quarto-listing")) return;
    const a = document.createElement("a");
    a.className = "anchorjs-link";
    a.href = "#" + h.dataset.anchorId;
    a.setAttribute("aria-label", "Anchor");
    h.appendChild(a);
  });

  // ---- the table of contents follows the reader
  const tocLinks = $$("#TOC a.nav-link");
  if (tocLinks.length) {
    const targets = tocLinks.map((a) => document.getElementById(decodeURIComponent(a.getAttribute("href").slice(1)))).filter(Boolean);
    const spy = () => {
      const top = (header ? header.offsetHeight : 0) + 24;
      let current = 0;
      targets.forEach((t, i) => { if (t.getBoundingClientRect().top - top <= 0) current = i; });
      if (window.innerHeight + window.scrollY >= document.body.scrollHeight - 2) current = targets.length - 1;
      tocLinks.forEach((a, i) => a.classList.toggle("active", i === current));
    };
    document.addEventListener("scroll", spy, { passive: true });
    spy();
  }

  // ---- maths, when KaTeX has loaded
  window.smalldocsMath = () => {
    if (!window.renderMathInElement) return;
    window.renderMathInElement(document.body, {
      delimiters: [{ left: "\\[", right: "\\]", display: true }, { left: "\\(", right: "\\)", display: false }],
      throwOnError: false,
    });
  };
  window.smalldocsMath();  // deferred scripts run in order, so KaTeX, when the page has maths, has loaded

  // ---- search
  let index = null, fuse = null;
  const loadIndex = async () => {
    if (index) return;
    try {
      const r = await fetch(offset + "search.json");
      index = await r.json();
    } catch (e) { index = []; }
    if (window.Fuse) {
      fuse = new window.Fuse(index, {
        keys: [{ name: "title", weight: 2 }, { name: "section", weight: 2 }, { name: "text", weight: 1 }],
        ignoreLocation: true, threshold: 0.3, minMatchCharLength: 2, includeMatches: false,
      });
    }
  };
  const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const snippet = (text, q) => {
    const i = text.toLowerCase().indexOf(q.toLowerCase().split(/\s+/)[0] || "");
    const start = Math.max(0, i - 60);
    let s = escapeHtml(text.slice(start, start + 200));
    q.split(/\s+/).filter((w) => w.length > 1).forEach((w) => {
      s = s.replace(new RegExp("(" + w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig"), "<mark>$1</mark>");
    });
    return (start ? "…" : "") + s;
  };
  $$(".smalldocs-search").forEach((box) => {
    const input = $("input", box), results = $(".smalldocs-search-results", box);
    let active = -1;
    const show = (html) => { results.innerHTML = html; results.classList.add("show"); active = -1; };
    const hide = () => results.classList.remove("show");
    const run = async () => {
      const q = input.value.trim();
      if (q.length < 2) { hide(); return; }
      await loadIndex();
      const limit = parseInt(box.dataset.limit, 10) || 20;
      const hits = fuse ? fuse.search(q, { limit }).map((h) => h.item)
        : index.filter((e) => (e.title + " " + e.section + " " + e.text).toLowerCase().includes(q.toLowerCase())).slice(0, limit);
      if (!hits.length) { show('<div class="search-none">No results</div>'); return; }
      show(hits.map((e) => `<a class="search-result" href="${offset}${e.href}">` +
        `<div class="search-result-title">${escapeHtml(e.title)}</div>` +
        (e.section ? `<div class="search-result-section">${escapeHtml(e.section)}</div>` : "") +
        `<div class="search-result-text">${snippet(e.text, q)}</div></a>`).join(""));
    };
    let timer = null;
    input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, 120); });
    input.addEventListener("focus", () => { loadIndex(); if (input.value.trim().length > 1) run(); });
    input.addEventListener("keydown", (ev) => {
      const items = $$(".search-result", results);
      if (ev.key === "Escape") { hide(); input.blur(); return; }
      if (!items.length) return;
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        ev.preventDefault();
        active = (active + (ev.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
        items.forEach((it, i) => it.classList.toggle("active", i === active));
        items[active].scrollIntoView({ block: "nearest" });
      } else if (ev.key === "Enter") {
        ev.preventDefault();
        (items[active] || items[0]).click();
      }
    });
    document.addEventListener("click", (ev) => { if (!box.contains(ev.target)) hide(); });
  });
  // the keys that focus search: search.keyboard-shortcut when the site sets it, else / as before; Ctrl-K or Cmd-K too
  const keyed = $("[data-keyboard-shortcut]");
  let searchKeys = ["/"];
  try { if (keyed) searchKeys = JSON.parse(keyed.dataset.keyboardShortcut); } catch (e) { /* keep / */ }
  document.addEventListener("keydown", (ev) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) || document.activeElement.isContentEditable;
    const plain = !keyed || (!ev.metaKey && !ev.ctrlKey && !ev.altKey);  // with no keys set, any / goes to search, as before
    if ((plain && searchKeys.includes(ev.key) && !typing) || ((ev.metaKey || ev.ctrlKey) && ev.key === "k")) {
      const box = $$(".smalldocs-search").find((b) => b.offsetParent !== null);
      if (box && box.classList.contains("sd-search-overlay")) box.classList.add("sd-open");
      const input = box && $("input", box);
      if (input) { ev.preventDefault(); input.focus(); }
    }
  });

  // ---- listings: categories, filter, sort and pages
  const listings = $$(".quarto-listing");
  const categoryFromHash = () => {
    const m = location.hash.match(/^#category=(.*)$/);
    return m ? decodeURIComponent(m[1]) : "";
  };
  const state = new Map();
  const refresh = (listing) => {
    const st = state.get(listing);
    const items = $$("[data-index]", listing);
    const cat = categoryFromHash();
    const q = st.filter.toLowerCase();
    let shown = items.filter((it) => {
      const cats = JSON.parse(it.dataset.categories || "[]");
      return (!cat || cats.includes(cat)) && (!q || (it.dataset.text || "").includes(q));
    });
    if (st.sort) {
      const [field, way] = st.sort.split(":");
      const val = (it) => JSON.parse(it.dataset.sort || "{}")[field];
      shown.sort((a, b) => {
        const x = val(a), y = val(b);
        if (x === undefined) return 1;
        if (y === undefined) return -1;
        return (x < y ? -1 : x > y ? 1 : 0) * (way === "desc" ? -1 : 1);
      });
    } else {
      shown.sort((a, b) => a.dataset.index - b.dataset.index);
    }
    const parent = items.length ? items[0].parentElement : null;
    const size = Math.max(1, parseInt(listing.dataset.pageSize, 10) || 50);
    const pages = Math.max(1, Math.ceil(shown.length / size));
    st.page = Math.min(st.page, pages - 1);
    items.forEach((it) => { it.hidden = true; });
    shown.forEach((it, i) => {
      if (parent) parent.appendChild(it);
      it.hidden = Math.floor(i / size) !== st.page;
    });
    const none = $(".listing-no-matching", listing);
    if (none) none.classList.toggle("d-none", shown.length > 0);
    const nav = $(".listing-pagination", listing);
    if (nav) {
      nav.innerHTML = pages < 2 ? "" : Array.from({ length: pages }, (_, i) =>
        `<button type="button" class="btn btn-sm ${i === st.page ? "btn-primary" : "btn-outline-secondary"}" data-page="${i}">${i + 1}</button>`).join("");
    }
    $$(".quarto-listing-category .category").forEach((c) => c.classList.toggle("active", (c.dataset.category || "") === cat));
  };
  listings.forEach((listing) => {
    state.set(listing, { filter: "", sort: "", page: 0 });
    const f = $(".listing-filter", listing), s = $(".listing-sort", listing), nav = $(".listing-pagination", listing);
    if (f) f.addEventListener("input", () => { state.get(listing).filter = f.value; state.get(listing).page = 0; refresh(listing); });
    if (s) s.addEventListener("change", () => { state.get(listing).sort = s.value; refresh(listing); });
    if (nav) nav.addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-page]");
      if (!b) return;
      state.get(listing).page = parseInt(b.dataset.page, 10);
      refresh(listing);
      listing.scrollIntoView({ block: "start" });
    });
    refresh(listing);
  });
  const setCategory = (cat) => {
    history.replaceState(null, "", cat ? "#category=" + encodeURIComponent(cat) : location.pathname + location.search);
    listings.forEach((l) => { state.get(l).page = 0; refresh(l); });
  };
  document.addEventListener("click", (ev) => {
    const c = ev.target.closest(".listing-category, .quarto-listing-category .category");
    if (!c || !listings.length) return;
    ev.preventDefault();
    const cat = c.dataset.category || "";
    setCategory(cat === categoryFromHash() && c.classList.contains("listing-category") ? "" : cat);
  });
  window.addEventListener("hashchange", () => listings.forEach(refresh));

  // ---- Quarto features: Markdown
  // Tabsets with the same `group`: a tab chosen in one shows the tab of the same name in the others, and the page
  // remembers the choice, under Quarto's own key
  const tabKey = "quarto-persistent-tabsets-data";
  const readTabs = () => { try { return JSON.parse(store.get(tabKey) || "{}") || {}; } catch (e) { return {}; } };
  const grouped = $$(".panel-tabset[data-group]");
  const tabLinks = (set) => $$(":scope > .nav-tabs .nav-link", set);
  const showTab = (group, name) => grouped.filter((s) => s.dataset.group === group).forEach((set) => {
    const links = tabLinks(set);
    const hit = links.find((a) => a.textContent.trim() === name);
    if (!hit) return;
    links.forEach((a) => {
      const on = a === hit;
      a.classList.toggle("active", on);
      a.setAttribute("aria-selected", on ? "true" : "false");
      const pane = document.getElementById(a.getAttribute("aria-controls"));
      if (pane) pane.classList.toggle("active", on);
    });
  });
  grouped.forEach((set) => tabLinks(set).forEach((a) => a.addEventListener("click", () => {
    const name = a.textContent.trim(), data = readTabs();
    data[set.dataset.group] = name;
    store.set(tabKey, JSON.stringify(data));
    showTab(set.dataset.group, name);
  })));
  if (grouped.length) Object.entries(readTabs()).forEach(([group, name]) => showTab(group, name));

  // ---- Quarto features: page and site

  // toc-expand: the levels below the setting open for the section the reader is in
  const tocNav = $("#TOC[data-toc-expanded]");
  if (tocNav) {
    const expandToc = () => {
      $$("ul.collapse", tocNav).forEach((u) => u.classList.remove("show"));
      const on = $("a.nav-link.active", tocNav);
      if (!on) return;
      const own = on.parentElement.querySelector(":scope > ul.collapse");
      if (own) own.classList.add("show");
      for (let el = on.parentElement; el && el !== tocNav; el = el.parentElement) {
        if (el.matches("ul.collapse")) el.classList.add("show");
      }
    };
    document.addEventListener("scroll", expandToc, { passive: true });
    expandToc();
  }

  // pinned: false hides the header while the reader scrolls down, and shows it when they scroll up
  if (header && header.classList.contains("sd-headroom")) {
    let last = window.scrollY;
    document.addEventListener("scroll", () => {
      const y = window.scrollY;
      if (y > last + 5 && y > header.offsetHeight) {
        header.classList.add("sd-header-hidden");
        document.documentElement.style.setProperty("--sd-header-height", "0px");
        document.documentElement.style.scrollPaddingTop = "16px";
      } else if (y < last - 5 || y <= 0) {
        header.classList.remove("sd-header-hidden");
        setHeader();
      }
      last = y;
    }, { passive: true });
  }

  // search.type: overlay: the icon opens the search box, and the box closes when it is empty and loses focus
  $$(".sd-search-overlay").forEach((box) => {
    const btn = $(".sd-search-toggle", box), input = $("input", box);
    const close = () => { if (!input.value) { box.classList.remove("sd-open"); btn.setAttribute("aria-expanded", "false"); } };
    btn.addEventListener("click", () => {
      const open = !box.classList.contains("sd-open");
      box.classList.toggle("sd-open", open);
      btn.setAttribute("aria-expanded", String(open));
      if (open) input.focus();
    });
    input.addEventListener("blur", () => setTimeout(close, 200));
    input.addEventListener("keydown", (ev) => { if (ev.key === "Escape") { input.value = ""; close(); } });
  });

  // back-to-top-navigation: the link shows as the reader scrolls up, and at the end of the page, as in Quarto
  const toTop = $("#quarto-back-to-top");
  if (toTop) {
    let lastTop = window.scrollY;
    document.addEventListener("scroll", () => {
      const y = window.scrollY;
      if (y - 5 > lastTop) { toTop.style.display = "none"; lastTop = Math.max(0, y); }
      else if (y < lastTop - 35) { toTop.style.display = "inline-block"; lastTop = Math.max(0, y); }
      if (y <= 0) toTop.style.display = "none";
      else if (window.innerHeight + y >= document.body.offsetHeight) toTop.style.display = "inline-block";
    }, { passive: true });
  }

  // link-external-icon and link-external-filter: mark each link to another site; the filter names links that are not
  const main = $("main.content");
  if (main && (main.dataset.externalIcon || main.dataset.externalFilter)) {
    let filter = null;
    try { if (main.dataset.externalFilter) filter = new RegExp(main.dataset.externalFilter); } catch (e) { filter = null; }
    const internal = (a) => !/^https?:$/.test(a.protocol) || a.host === location.host || (filter && filter.test(a.href));
    $$("a[href]", main).forEach((a) => {
      if (a.matches(".nav-link, .no-external, .anchorjs-link, .pagination-link, .toc-action, [aria-hidden]")) return;
      if (internal(a)) {
        if (filter && filter.test(a.href) && a.target === "_blank") a.removeAttribute("target");
        return;
      }
      if (main.dataset.externalIcon) a.classList.add("external");
    });
  }

  // giscus follows the light or dark mode of the page
  const giscusTheme = () => {
    const frame = $("iframe.giscus-frame"), base = $("#giscus-base-theme"), alt = $("#giscus-alt-theme");
    if (!frame || !base || !alt) return;
    const theme = document.documentElement.classList.contains("quarto-dark") ? alt.value : base.value;
    frame.contentWindow.postMessage({ giscus: { setConfig: { theme } } }, "https://giscus.app");
  };
  if ($("#giscus-base-theme") && window.MutationObserver) {
    new MutationObserver(giscusTheme).observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  }
})();

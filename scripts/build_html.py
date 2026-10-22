#!/usr/bin/env python3
"""Render README + book/*.md into one self-contained reading page: guide.html."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "guide.html"

chapters = [{"id": "readme", "title": "About this book", "md": (ROOT / "README.md").read_text(encoding="utf-8")}]
for path in sorted((ROOT / "book").glob("[0-9][0-9]-*.md")):
    text = path.read_text(encoding="utf-8")
    title = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), path.stem)
    chapters.append({"id": path.stem, "title": title, "md": text})

data = json.dumps(chapters).replace("</", "<\\/")

HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>.NET Interview Guide</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css" media="(prefers-color-scheme: light)">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css" media="(prefers-color-scheme: dark)">
<style>
:root { --bg:#fbfaf7; --fg:#1d1f23; --muted:#5d6470; --side:#f1efe9; --line:#dedad0; --accent:#2f5fb3; --code:#f2f0ea; }
@media (prefers-color-scheme: dark) { :root { --bg:#16181c; --fg:#e4e6ea; --muted:#9aa1ad; --side:#1d2026; --line:#2e333b; --accent:#7fa7ee; --code:#20242b; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:17px/1.65 Georgia, "Iowan Old Style", serif; }
nav { position:fixed; top:0; left:0; bottom:0; width:300px; overflow-y:auto; background:var(--side); border-right:1px solid var(--line); padding:20px 14px; font:14px/1.4 -apple-system, system-ui, sans-serif; }
nav h1 { font-size:15px; margin:0 0 14px; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }
nav a { display:block; padding:7px 10px; border-radius:6px; color:var(--fg); text-decoration:none; }
nav a:hover { background:var(--line); }
nav a.active { background:var(--accent); color:#fff; }
nav .toc a { padding:3px 10px 3px 22px; font-size:13px; color:var(--muted); }
main { margin-left:300px; padding:40px 48px 120px; }
article { max-width:820px; margin:0 auto; }
h1,h2,h3,h4 { font-family:-apple-system, system-ui, sans-serif; line-height:1.3; }
h1 { font-size:30px; } h2 { margin-top:2.2em; border-bottom:1px solid var(--line); padding-bottom:6px; }
a { color:var(--accent); }
code { font:14px/1.5 ui-monospace, "SF Mono", Menlo, monospace; background:var(--code); padding:1px 5px; border-radius:4px; }
pre { background:var(--code); padding:14px 16px; border-radius:8px; overflow-x:auto; }
pre code { padding:0; background:none; }
pre code.hljs { background:none; padding:0; }
table { border-collapse:collapse; display:block; overflow-x:auto; font-size:15px; margin:1em 0; }
th,td { border:1px solid var(--line); padding:6px 10px; vertical-align:top; }
th { background:var(--side); }
blockquote { margin:1em 0; padding:4px 16px; border-left:4px solid var(--accent); background:var(--side); }
details { background:var(--side); border:1px solid var(--line); border-radius:8px; padding:8px 14px; margin:1em 0; }
summary { cursor:pointer; font-weight:600; font-family:-apple-system, system-ui, sans-serif; }
.mermaid { background:#fff; border-radius:8px; padding:12px; text-align:center; }
.pager { display:flex; justify-content:space-between; margin-top:60px; font-family:-apple-system, system-ui, sans-serif; }
#menu { display:none; }
@media (max-width: 900px) {
  nav { transform:translateX(-100%); transition:transform .2s; z-index:10; }
  nav.open { transform:none; }
  main { margin-left:0; padding:56px 16px 80px; }
  #menu { display:block; position:fixed; top:10px; left:10px; z-index:11; padding:6px 12px; border-radius:6px; border:1px solid var(--line); background:var(--side); color:var(--fg); }
}
</style>
</head>
<body>
<button id="menu">Chapters</button>
<nav id="nav"><h1>.NET Interview Guide</h1><div id="links"></div></nav>
<main><article id="content"></article></main>
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.2/marked.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/csharp.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<script>
const CHAPTERS = __DATA__;
mermaid.initialize({ startOnLoad:false, theme:"default", securityLevel:"strict" });
const slug = s => s.toLowerCase().replace(/<[^>]+>/g,"").replace(/[^\\w\\s-]/g,"").trim().replace(/\\s+/g,"-");
const renderer = new marked.Renderer();
renderer.heading = (text, level, raw) => `<h${level} id="${slug(raw)}">${text}</h${level}>`;
renderer.code = (code, lang) => lang === "mermaid"
  ? `<div class="mermaid">${code.replace(/</g,"&lt;")}</div>`
  : `<pre><code class="language-${lang || "plaintext"}">${code.replace(/&/g,"&amp;").replace(/</g,"&lt;")}</code></pre>`;
renderer.link = (href, title, text) => {
  const m = href && href.match(/(?:^|\\/)(\\d\\d-[\\w-]+)\\.md(#.*)?$/);
  if (m) href = "#" + m[1];
  else if (href && href.endsWith(".txt")) href = href;
  return `<a href="${href}">${text}</a>`;
};
marked.use({ renderer, gfm:true });

function show(id) {
  const ch = CHAPTERS.find(c => c.id === id) || CHAPTERS[0];
  const i = CHAPTERS.indexOf(ch);
  const prev = CHAPTERS[i-1], next = CHAPTERS[i+1];
  document.getElementById("content").innerHTML = marked.parse(ch.md) +
    `<div class="pager">${prev ? `<a href="#${prev.id}">&larr; ${prev.title}</a>` : "<span></span>"}${next ? `<a href="#${next.id}">${next.title} &rarr;</a>` : ""}</div>`;
  document.querySelectorAll("pre code").forEach(el => hljs.highlightElement(el));
  mermaid.run({ querySelector: ".mermaid" }).catch(() => {});
  const toc = [...document.querySelectorAll("#content h2")].map(h => `<a href="#${ch.id}/${h.id}">${h.textContent}</a>`).join("");
  document.getElementById("links").innerHTML = CHAPTERS.map(c =>
    `<a href="#${c.id}" class="${c.id === ch.id ? "active" : ""}">${c.title}</a>` + (c.id === ch.id ? `<div class="toc">${toc}</div>` : "")).join("");
  try { localStorage.setItem("guide-last", location.hash); } catch (e) {}
}
function route() {
  const [id, anchor] = location.hash.slice(1).split("/");
  show(id);
  document.getElementById("nav").classList.remove("open");
  if (anchor) document.getElementById(anchor)?.scrollIntoView(); else window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);
document.getElementById("menu").onclick = () => document.getElementById("nav").classList.toggle("open");
if (!location.hash) { try { const last = localStorage.getItem("guide-last"); if (last) location.hash = last; } catch (e) {} }
route();
</script>
</body>
</html>
"""

OUT.write_text(HTML.replace("__DATA__", data), encoding="utf-8")
print(f"{OUT}: {len(chapters)} sections")

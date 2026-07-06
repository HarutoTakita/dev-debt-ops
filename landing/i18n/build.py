#!/usr/bin/env python3
"""landing/i18n/{en,zh,ko,es,de}.json から landing/i18n.js を生成する。
ja は index.html の DOM を baseline として使うため辞書には含めない。
実行: cd landing && python3 i18n/build.py"""
import json
import os

HERE = os.path.dirname(__file__)
LANGS = ["en", "zh", "ko", "es", "de"]

ja = json.load(open(os.path.join(HERE, "ja-source.json"), encoding="utf-8"))
jak = set(ja)
dicts = {}
for l in LANGS:
    d = json.load(open(os.path.join(HERE, f"{l}.json"), encoding="utf-8"))
    miss = jak - set(d)
    if miss:
        raise SystemExit(f"{l}.json missing keys: {sorted(miss)[:10]}")
    dicts[l] = d

RUNTIME = r"""// 多言語切り替え（landing/i18n/*.json から build.py で自動生成。編集は json を直して再生成）。
// ja は index.html の DOM を baseline に、en/zh/ko/es/de を切替時に innerHTML へ適用。
// 選択言語は PARAGLIDE_LOCALE cookie(path=/)+localStorage に保存しアプリ側 Paraglide に引き継ぐ。
(function () {
  var LOCALES = ["ja", "en", "zh", "ko", "es", "de"];
  var NAMES = { ja: "日本語", en: "English", zh: "中文", ko: "한국어", es: "Español", de: "Deutsch" };
  var COOKIE = "PARAGLIDE_LOCALE";
  var DICT = __DICT__;

  function getCookie(name) {
    var m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : null;
  }
  function persist(loc) {
    document.cookie = COOKIE + "=" + loc + "; path=/; max-age=31536000; samesite=lax";
    try { localStorage.setItem(COOKIE, loc); } catch (e) {}
  }
  function detect() {
    var c = getCookie(COOKIE);
    if (LOCALES.indexOf(c) >= 0) return c;
    try {
      var ls = localStorage.getItem(COOKIE);
      if (LOCALES.indexOf(ls) >= 0) return ls;
    } catch (e) {}
    return "ja";
  }

  var baseline = {};
  function cacheBaseline() {
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      baseline[el.getAttribute("data-i18n")] = el.innerHTML;
    });
  }
  function apply(loc) {
    var dict = DICT[loc];
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      var k = el.getAttribute("data-i18n");
      var v = loc === "ja" || !dict ? baseline[k] : dict[k] != null ? dict[k] : baseline[k];
      if (v != null) el.innerHTML = v;
    });
    document.documentElement.setAttribute("lang", loc);
  }

  // shadcn DropdownMenu 風カスタムドロップダウンの UI 更新。
  function updateSwitcher(loc) {
    var cur = document.getElementById("lang-current");
    if (cur) cur.textContent = NAMES[loc] || loc;
    document.querySelectorAll("#lang-menu .lang-opt").forEach(function (btn) {
      var chk = btn.querySelector(".lang-check");
      if (chk) chk.style.visibility = btn.getAttribute("data-locale") === loc ? "visible" : "hidden";
    });
  }
  function openMenu(open) {
    var menu = document.getElementById("lang-menu");
    var trig = document.getElementById("lang-trigger");
    if (!menu || !trig) return;
    if (open) { menu.classList.remove("hidden"); trig.setAttribute("aria-expanded", "true"); }
    else { menu.classList.add("hidden"); trig.setAttribute("aria-expanded", "false"); }
  }
  function setLocale(loc) {
    if (LOCALES.indexOf(loc) < 0) loc = "ja";
    persist(loc);
    apply(loc);
    updateSwitcher(loc);
  }

  function init() {
    cacheBaseline();
    var loc = detect();
    var trig = document.getElementById("lang-trigger");
    var menu = document.getElementById("lang-menu");
    if (trig && menu) {
      trig.addEventListener("click", function (e) {
        e.stopPropagation();
        openMenu(menu.classList.contains("hidden"));
      });
      menu.querySelectorAll(".lang-opt").forEach(function (btn) {
        btn.addEventListener("click", function () {
          setLocale(btn.getAttribute("data-locale"));
          openMenu(false);
        });
      });
      document.addEventListener("click", function (e) {
        if (!e.target.closest("#lang-dd")) openMenu(false);
      });
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") openMenu(false);
      });
    }
    updateSwitcher(loc);
    if (loc !== "ja") apply(loc);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
"""

out = RUNTIME.replace("__DICT__", json.dumps(dicts, ensure_ascii=False, separators=(",", ":")))
open(os.path.join(HERE, "..", "i18n.js"), "w", encoding="utf-8").write(out)
print("i18n.js generated:", len(out), "bytes")

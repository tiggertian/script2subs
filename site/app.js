// Point the download button at the newest release DMG. Falls back to the
// releases page (already set in the HTML) if the API is rate-limited.
(function () {
  var REPO = "tiggertian/script2subs";
  var btn = document.getElementById("download");
  var meta = document.getElementById("download-meta");
  if (!btn) return;

  fetch("https://api.github.com/repos/" + REPO + "/releases/latest", {
    headers: { "Accept": "application/vnd.github+json" }
  })
    .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
    .then(function (release) {
      var tag = release.tag_name || "";
      var assets = release.assets || [];
      var dmg = assets.find(function (a) {
        return /\.dmg$/i.test(a.name);
      });
      if (dmg) {
        btn.href = dmg.browser_download_url;
        if (meta) meta.textContent = dmg.name + (tag ? " \u00b7 " + tag : "");
      } else if (meta && tag) {
        meta.textContent = "Latest release " + tag;
      }
    })
    .catch(function () {
      if (meta) meta.textContent = "See all releases on GitHub";
    });
})();

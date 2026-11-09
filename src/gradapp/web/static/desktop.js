// Loaded only inside the GradApp app window (see gradapp.desktop). Not used in a normal browser tab.
(function () {
  var cfg = window.__DESKTOP__ || {};
  var isExternal = function (u) {
    try { var x = new URL(u, location.href); return /^https?:$/.test(x.protocol) && x.origin !== location.origin; } catch (e) { return false; }
  };
  var openOutside = function (u) {
    fetch('/api/open-external', { method: 'POST', headers: { 'X-GradApp': '1', 'Content-Type': 'application/json' }, body: JSON.stringify({ url: u }) }).catch(function () {});
  };
  // official pages and professor pages open in the real browser, not inside the app window
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href]');
    if (a && isExternal(a.href)) { e.preventDefault(); openOutside(a.href); }
  }, true);
  var nativeOpen = window.open;
  window.open = function (u) {
    if (u && isExternal(u)) { openOutside(u); return null; }
    return nativeOpen.apply(window, arguments);
  };
  // tell the server this window is closing (a reload or page change sends it too; the server waits a moment and sees the next request)
  window.addEventListener('pagehide', function () {
    try { navigator.sendBeacon('/desktop/bye?t=' + encodeURIComponent(cfg.token || '')); } catch (e) {}
  });
  // keeps the server informed that the window is alive, and backs up the close signal if it gets lost
  if (cfg.heartbeat) setInterval(function () { fetch('/healthz', { cache: 'no-store' }).catch(function () {}); }, 20000);
})();

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
  // lets the server quit itself when this page is closed and it cannot watch the window process
  if (cfg.heartbeat) setInterval(function () { fetch('/healthz', { cache: 'no-store' }).catch(function () {}); }, 20000);
})();

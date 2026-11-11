// ES5 only: this runs on TV browsers as old as Chromium 63.
(function () {
  'use strict';

  var MAX_LINES = 3;        // the budget; see README
  var STALE_MINUTES = 15;   // older data is hidden rather than shown wrong
  var POLL_MS = 60000;
  var KEY = { LEFT: 37, UP: 38, RIGHT: 39, DOWN: 40, OK: 13, ESC: 27, BACKSPACE: 8, TV_BACK: 10009 };
  var DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                'August', 'September', 'October', 'November', 'December'];

  function $(id) { return document.getElementById(id); }

  // ---- settings: defaults, overridden by ?screen=<name>
  var cfg = window.QUIET_CONFIG || {};
  var match = /[?&]screen=([^&]*)/.exec(location.search);
  var screen = (cfg.screens || {})[match ? decodeURIComponent(match[1]) : ''] || {};
  var S = {};
  var k;
  for (k in cfg.defaults) { if (cfg.defaults.hasOwnProperty(k)) { S[k] = cfg.defaults[k]; } }
  for (k in screen) { if (screen.hasOwnProperty(k)) { S[k] = screen[k]; } }
  S.art = S.art || [];
  S.apps = S.apps || [];
  if (!S.whisper) { document.body.className += ' nowhisper'; }

  // ---- modes: art -> glance -> play, always falling back to art
  var mode = 'art';
  var idleTimer = null;
  var focus = 0;

  function setMode(next, seconds) {
    mode = next;
    document.body.className = document.body.className.replace(/\b(art|glance|play)\b/, next);
    clearTimeout(idleTimer);
    if (next !== 'art') {
      idleTimer = setTimeout(function () { setMode('art'); }, (seconds || S.glanceSeconds) * 1000);
    }
  }

  // ---- clock
  function tick() {
    var d = new Date();
    var m = d.getMinutes();
    var t = (d.getHours() % 12 || 12) + ':' + (m < 10 ? '0' : '') + m;
    if ($('time').textContent !== t) {
      $('time').textContent = t;
      $('whisper').textContent = t;
      $('date').textContent = DAYS[d.getDay()] + ', ' + MONTHS[d.getMonth()] + ' ' + d.getDate();
      showArt();
    }
  }

  // ---- art: picked from the clock, so every screen shows the same piece
  var artIndex = -1;
  function showArt() {
    if (!S.art.length) { return; }
    var i = Math.floor(Date.now() / (S.artMinutes * 60000)) % S.art.length;
    if (i === artIndex) { return; }
    artIndex = i;
    var a = $('artA'), b = $('artB');
    var front = /\bon\b/.test(a.className) ? a : b;
    var back = front === a ? b : a;
    if (!front.getAttribute('src')) { front.src = S.art[i]; return; }
    back.onload = function () {
      back.className = 'art on';
      front.className = 'art';
    };
    back.src = S.art[i];
  }

  // ---- state: one small JSON file, polled
  var lastAlert = '';
  function render(data) {
    var lines = (data && data.lines) || [];
    if (data && data.updated && Date.now() - new Date(data.updated).getTime() > STALE_MINUTES * 60000) {
      lines = [];
    }
    var ul = $('lines');
    while (ul.firstChild) { ul.removeChild(ul.firstChild); }
    for (var i = 0; i < lines.length && i < MAX_LINES; i++) {
      var li = document.createElement('li');
      var label = document.createElement('span');
      label.className = 'label';
      label.textContent = lines[i].label || '';
      li.appendChild(label);
      li.appendChild(document.createTextNode(lines[i].text || ''));
      ul.appendChild(li);
    }
    var alert = (data && data.alert) || '';
    $('alert').textContent = alert;
    if (alert && alert !== lastAlert) { setMode('glance', 45); }
    lastAlert = alert;
  }

  function poll() {
    var x = new XMLHttpRequest();
    x.open('GET', S.stateUrl + (S.stateUrl.indexOf('?') < 0 ? '?' : '&') + 't=' + Date.now());
    x.timeout = 10000;
    x.onload = function () {
      var data = null;
      try { if (x.status === 200) { data = JSON.parse(x.responseText); } } catch (e) {}
      render(data);
    };
    x.onerror = x.ontimeout = function () { render(null); };
    x.send();
  }

  // ---- play: a row of app names
  function drawDock() {
    var ul = $('dock');
    for (var i = 0; i < S.apps.length; i++) {
      var li = document.createElement('li');
      li.textContent = S.apps[i].name;
      li.onclick = (function (n) {
        return function (e) { e.stopPropagation(); launch(S.apps[n]); };
      })(i);
      ul.appendChild(li);
    }
    moveFocus(0);
  }

  function moveFocus(step) {
    var items = $('dock').children;
    if (!items.length) { return; }
    focus = Math.max(0, Math.min(items.length - 1, focus + step));
    for (var i = 0; i < items.length; i++) { items[i].className = i === focus ? 'focus' : ''; }
  }

  function launch(app) {
    if (!app) { return; }
    if (window.tizen && app.tizen) {
      window.tizen.application.launch(app.tizen, function () {}, function () {});
    } else if (app.url) {
      location.href = app.url;
    }
  }

  // ---- input: remote, keyboard, touch
  document.addEventListener('keydown', function (e) {
    var c = e.keyCode;
    var back = c === KEY.TV_BACK || c === KEY.ESC || c === KEY.BACKSPACE;
    if (mode === 'art') {
      if (!back) { setMode('glance'); }
      return;
    }
    e.preventDefault();
    if (back) { setMode('art'); return; }
    if (mode === 'glance') {
      setMode((c === KEY.DOWN || c === KEY.OK) && S.apps.length ? 'play' : 'glance');
      return;
    }
    if (c === KEY.UP) { setMode('glance'); return; }
    if (c === KEY.OK) { launch(S.apps[focus]); return; }
    if (c === KEY.LEFT) { moveFocus(-1); }
    if (c === KEY.RIGHT) { moveFocus(1); }
    setMode('play');
  });

  document.addEventListener('click', function () {
    if (mode === 'art') { setMode('glance'); }
    else if (mode === 'glance' && S.apps.length) { setMode('play'); }
    else { setMode('art'); }
  });

  drawDock();
  tick();
  setInterval(tick, 1000);
  poll();
  setInterval(poll, POLL_MS);
})();

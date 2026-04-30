"""apply_round3.py — patch viewer.html with Epic 10 Round 3b features.

Adds 5 features in fenced regions (EPIC10R3_MARK):
 1. Scene staging modal (Story 10.3)
 2. Portraits everywhere (Story 10.6)
 3. Sound design (Story 10.8)
 4. End-of-day highlight reel (Story 10.9 viewer)
 5. Daily gossip headlines ticker (Story 10.10 viewer)

Run from project root:
    .venv/Scripts/python.exe scripts/apply_round3.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.viewer_edit import ViewerBundle  # noqa: E402

VIEWER = ROOT / "viewer.html"


CSS_BLOCK = r"""
/* === EPIC10R3_MARK — Stories 10.3/10.6/10.8/10.9/10.10 === BEGIN */

/* 10.6 — avatar thumbnail used across feed/spotlight/recap */
.avatar-thumbnail {
  width:18px; height:18px; border-radius:50%;
  display:inline-block; vertical-align:middle;
  object-fit:cover; flex:0 0 auto;
  background:#222; border:2px solid rgba(255,255,255,0.18);
}
.avatar-thumbnail.fallback {
  display:inline-flex; align-items:center; justify-content:center;
  font:600 9px Inter,sans-serif; color:#fff; text-transform:uppercase;
}

/* 10.3 — scene staging modal */
#scene-modal {
  position:fixed; inset:0; z-index:80;
  background:rgba(12,13,20,0.85);
  display:none; align-items:center; justify-content:center;
  opacity:0; transition:opacity 300ms ease-out;
  font-family:'Inter',sans-serif;
}
#scene-modal.visible { display:flex; opacity:1; }
#scene-modal.fading  { opacity:0; transition:opacity 400ms ease-in; }
#scene-modal .scene-card {
  background:rgba(20,22,30,0.96);
  border:1px solid rgba(170,154,240,0.35);
  border-radius:14px; padding:24px 28px;
  width:min(560px, 92vw); color:#eef0f4;
  box-shadow:0 24px 60px rgba(0,0,0,0.55);
  display:flex; flex-direction:column; gap:14px;
}
#scene-modal .scene-portraits {
  display:flex; gap:18px; align-items:center; justify-content:center;
}
#scene-modal .scene-portraits img,
#scene-modal .scene-portraits .scene-fallback {
  width:96px; height:96px; border-radius:50%; object-fit:cover;
  border:3px solid rgba(170,154,240,0.55);
  background:#322;
}
#scene-modal .scene-portraits .scene-fallback {
  display:flex; align-items:center; justify-content:center;
  font:600 32px Inter,sans-serif; color:#fff;
}
#scene-modal .scene-vs {
  font-family:'Instrument Serif',serif; font-style:italic;
  color:#a99af0; font-size:18px;
}
#scene-modal .scene-caption {
  font-family:'Instrument Serif',serif; font-style:italic;
  text-align:center; font-size:18px; color:#cfc4f0;
  border-top:1px solid rgba(170,154,240,0.18);
  border-bottom:1px solid rgba(170,154,240,0.18);
  padding:8px 4px;
}
#scene-modal .scene-dialogue {
  min-height:48px; font-size:15px; line-height:1.45;
  color:#e8e9ee; text-align:center;
  font-family:'Instrument Serif',serif; font-style:italic;
}
#scene-modal .scene-skip {
  align-self:flex-end; background:transparent;
  border:1px solid rgba(180,180,220,0.3); color:#bdbecf;
  border-radius:6px; padding:3px 9px; font-size:11px; cursor:pointer;
}

#replay-scene-btn {
  display:inline-flex; align-items:center;
  background:rgba(40,30,80,0.45); color:#e8e9ee;
  border:1px solid rgba(180,180,220,0.25);
  border-radius:999px; padding:4px 10px;
  font-size:11px; font-weight:600; cursor:pointer;
  font-family:'Inter',sans-serif;
}
#replay-scene-btn:disabled { opacity:0.4; cursor:not-allowed; }

/* 10.8 — audio toggle + popover */
#audio-toggle {
  display:inline-flex; align-items:center;
  background:rgba(40,30,80,0.45); color:#e8e9ee;
  border:1px solid rgba(180,180,220,0.25);
  border-radius:999px; padding:4px 10px;
  font-size:11px; font-weight:600; cursor:pointer;
  font-family:'Inter',sans-serif;
}
#audio-toggle.active { background:rgba(120,80,200,0.55); border-color:#a99af0; }
#audio-popover {
  position:absolute; top:48px; right:14px;
  background:rgba(18,20,28,0.96); color:#eef0f4;
  border:1px solid rgba(170,154,240,0.35);
  border-radius:8px; padding:10px 12px;
  display:none; z-index:60;
  font-family:'Inter',sans-serif; font-size:11px;
  width:220px;
}
#audio-popover.visible { display:block; }
#audio-popover label { display:flex; align-items:center; gap:6px; margin:4px 0; }
#audio-popover input[type=range] { flex:1; }

/* 10.9 — highlight reel */
#highlight-reel {
  position:fixed; inset:0; z-index:75;
  background:rgba(8,9,14,0.92);
  display:none; align-items:center; justify-content:center;
  font-family:'Inter',sans-serif; color:#eef0f4;
}
#highlight-reel.visible { display:flex; }
#highlight-reel .reel-card {
  width:min(620px, 94vw);
  background:rgba(22,24,34,0.96);
  border:1px solid rgba(170,154,240,0.35);
  border-radius:14px; padding:32px 36px;
  text-align:center;
  display:flex; flex-direction:column; gap:14px; align-items:center;
}
#highlight-reel .reel-title {
  font-family:'Instrument Serif',serif; font-size:26px;
}
#highlight-reel .reel-portraits {
  display:flex; gap:14px; justify-content:center;
}
#highlight-reel .reel-portraits img,
#highlight-reel .reel-portraits .scene-fallback {
  width:64px; height:64px; border-radius:50%; object-fit:cover;
  border:2px solid rgba(170,154,240,0.55);
}
#highlight-reel .reel-caption {
  font-family:'Instrument Serif',serif; font-style:italic;
  font-size:16px; color:#dcd4f5;
}
#highlight-reel .reel-progress {
  width:100%; height:3px; background:rgba(60,60,90,0.5);
  border-radius:2px; overflow:hidden;
}
#highlight-reel .reel-progress > div {
  height:100%; background:linear-gradient(90deg,#a99af0,#7fc7d4);
  transform-origin:left center;
}
#highlight-reel .reel-skip {
  font-size:11px; color:#888; margin-top:6px;
}

/* 10.10 — gossip headlines ticker */
#gossip-ticker {
  position:relative;
  height:24px; line-height:24px;
  background:var(--surface, rgba(28,30,40,0.85));
  border-bottom:1px solid rgba(120,120,150,0.15);
  border-left:3px solid var(--accent, #a99af0);
  overflow:hidden;
  font-family:'Inter',sans-serif; font-size:12px; color:#cfd2dc;
  display:none;
  padding-left:10px;
}
#gossip-ticker.visible { display:block; }
#gossip-ticker .ticker-line {
  position:absolute; left:14px; right:14px; top:0;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
  transition: transform 400ms ease-out, opacity 400ms ease-out;
}
#gossip-ticker .ticker-line.entering { transform:translateX(40px); opacity:0; }
#gossip-ticker .ticker-line.leaving  { transform:translateX(-40px); opacity:0; }

/* === EPIC10R3_MARK === END */
"""


HUD_BUTTON_HTML = (
    '<button id="audio-toggle" title="Toggle audio">🔇</button>'
    '<button id="replay-scene-btn" title="Replay last scene" disabled>🎬 Replay</button>'
)


SCENE_MODAL_HTML = """
<!-- === EPIC10R3_MARK: scene staging === BEGIN -->
<div id="scene-modal" role="dialog" aria-label="Scene">
  <div class="scene-card">
    <div class="scene-portraits" id="scene-portraits"></div>
    <div class="scene-caption" id="scene-caption">—</div>
    <div class="scene-dialogue" id="scene-dialogue"></div>
    <button class="scene-skip" id="scene-skip">Dismiss (Esc)</button>
  </div>
</div>

<div id="audio-popover">
  <div style="font-weight:600;margin-bottom:6px">Audio</div>
  <label>Master <input type="range" id="aud-master" min="0" max="100" value="30"></label>
  <label><input type="checkbox" id="aud-mute-ambient"> Mute ambient</label>
  <label><input type="checkbox" id="aud-mute-ui"> Mute UI</label>
  <label><input type="checkbox" id="aud-mute-stings"> Mute stings</label>
</div>

<div id="highlight-reel">
  <div class="reel-card">
    <div class="reel-title" id="reel-title">Day —</div>
    <div class="reel-portraits" id="reel-portraits"></div>
    <div class="reel-caption" id="reel-caption">—</div>
    <div class="reel-progress"><div id="reel-progress-bar" style="transform:scaleX(0)"></div></div>
    <div class="reel-skip">Press Esc or click to skip</div>
  </div>
</div>
<!-- === EPIC10R3_MARK: scene staging === END -->
"""


GOSSIP_TICKER_HTML = (
    '<!-- === EPIC10R3_MARK: gossipTicker === BEGIN -->\n'
    '<div id="gossip-ticker"><div class="ticker-line" id="ticker-line">—</div></div>\n'
    '<!-- === EPIC10R3_MARK: gossipTicker === END -->\n'
)


JS_BLOCK = r"""

// === EPIC10R3_MARK — Round 3b viewer features === BEGIN

// ───── Story 10.6: avatar cache (used by all features below) ─────
const _avatarCache = new Map();
function _avatarHtml(name, size) {
  size = size || 18;
  const color = (typeof AGENT_COLORS !== 'undefined' && AGENT_COLORS[name]) || '#9b958a';
  const initial = (name || '?').charAt(0).toUpperCase();
  // We render an <img>; if it fails the onerror swaps to a fallback styled span.
  return `<img class="avatar-thumbnail" data-name="${name||''}" `
       + `style="width:${size}px;height:${size}px;border-color:${color}" `
       + `src="/api/agent/${name||''}/avatar" alt="${name||''}" `
       + `onerror="this.outerHTML='<span class=\\'avatar-thumbnail fallback\\' style=\\'width:${size}px;height:${size}px;background:${color}\\'>${initial}</span>'">`;
}
function _primeAvatarCache(names) {
  for (const n of (names || [])) {
    if (_avatarCache.has(n)) continue;
    const img = new Image();
    img.onload = () => _avatarCache.set(n, img);
    img.onerror = () => { /* swallow */ };
    img.src = '/api/agent/' + n + '/avatar';
    _avatarCache.set(n, img); // optimistic
  }
}


// ───── Story 10.8: Sound API ─────
const Sound = (function(){
  const channels = {
    ambient:  { src: 'static/audio/ambient_city.mp3',   loop: true,  el: null },
    ui_event: { src: 'static/audio/ui_event.mp3',       loop: false, el: null },
    ui_msg:   { src: 'static/audio/ui_message.mp3',     loop: false, el: null },
    sting_d:  { src: 'static/audio/sting_drama.mp3',    loop: false, el: null },
    sting_r:  { src: 'static/audio/sting_refusal.mp3',  loop: false, el: null },
    bell:     { src: 'static/audio/chime_dayboundary.mp3', loop: false, el: null },
  };
  let _on = false;
  let _master = parseInt(localStorage.getItem('aud_master') || '30', 10);
  const _mutes = {
    ambient: localStorage.getItem('aud_mute_ambient') === '1',
    ui:      localStorage.getItem('aud_mute_ui') === '1',
    stings:  localStorage.getItem('aud_mute_stings') === '1',
  };

  function _ensure(name) {
    const c = channels[name];
    if (!c) return null;
    if (c.el) return c.el;
    try {
      const a = new Audio(c.src);
      a.loop = c.loop;
      a.preload = 'auto';
      // Swallow load errors silently — files are BYO.
      a.addEventListener('error', () => {}, { once:true });
      c.el = a;
      return a;
    } catch (e) { return null; }
  }
  function _channelMuted(name) {
    if (name === 'ambient') return _mutes.ambient;
    if (name === 'ui_event' || name === 'ui_msg' || name === 'bell') return _mutes.ui;
    return _mutes.stings;
  }
  function _vol() { return Math.max(0, Math.min(1, _master / 100)); }
  function play(name) {
    if (!_on) return;
    if (_channelMuted(name)) return;
    const a = _ensure(name);
    if (!a) return;
    try {
      a.volume = _vol();
      if (!a.paused) a.currentTime = 0;
      a.play().catch(()=>{});
    } catch (e) {}
  }
  function setOn(v) {
    _on = !!v;
    const ambient = _ensure('ambient');
    if (ambient) {
      try {
        if (_on && !_mutes.ambient) { ambient.volume = _vol(); ambient.play().catch(()=>{}); }
        else { ambient.pause(); }
      } catch (e) {}
    }
  }
  function setMaster(v) {
    _master = v;
    localStorage.setItem('aud_master', String(v));
    for (const k of Object.keys(channels)) {
      if (channels[k].el) try { channels[k].el.volume = _vol(); } catch (e) {}
    }
  }
  function setMute(group, val) {
    _mutes[group] = !!val;
    localStorage.setItem('aud_mute_' + group, val ? '1' : '0');
    if (group === 'ambient') {
      const a = _ensure('ambient');
      if (a) {
        try { if (val) a.pause(); else if (_on) a.play().catch(()=>{}); } catch (e) {}
      }
    }
  }
  function isOn() { return _on; }
  return { play, setOn, setMaster, setMute, isOn, _mutes, _master:()=>_master };
})();

(function _wireAudioControls(){
  const tog = document.getElementById('audio-toggle');
  const pop = document.getElementById('audio-popover');
  const mas = document.getElementById('aud-master');
  if (mas) mas.value = String(Sound._master());
  const mAmb = document.getElementById('aud-mute-ambient');
  const mUI  = document.getElementById('aud-mute-ui');
  const mSt  = document.getElementById('aud-mute-stings');
  if (mAmb) mAmb.checked = !!Sound._mutes.ambient;
  if (mUI)  mUI.checked  = !!Sound._mutes.ui;
  if (mSt)  mSt.checked  = !!Sound._mutes.stings;

  if (tog) {
    tog.addEventListener('click', e => {
      // Single click = toggle, alt-click = open popover
      if (e.altKey || e.shiftKey) {
        if (pop) pop.classList.toggle('visible');
        return;
      }
      const newState = !Sound.isOn();
      Sound.setOn(newState);
      tog.classList.toggle('active', newState);
      tog.textContent = newState ? '🔊' : '🔇';
    });
    tog.addEventListener('contextmenu', e => {
      e.preventDefault();
      if (pop) pop.classList.toggle('visible');
    });
  }
  if (mas) mas.addEventListener('input', () => Sound.setMaster(parseInt(mas.value, 10)));
  if (mAmb) mAmb.addEventListener('change', () => Sound.setMute('ambient', mAmb.checked));
  if (mUI)  mUI.addEventListener('change',  () => Sound.setMute('ui',      mUI.checked));
  if (mSt)  mSt.addEventListener('change',  () => Sound.setMute('stings',  mSt.checked));
})();


// ───── Story 10.6: portrait sweep — feed + spotlight + narration ─────
(function _portraitSweep(){
  // Wrap renderFeed: add 18px avatar at start of each line.
  if (typeof renderFeed === 'function') {
    const _prev = renderFeed;
    renderFeed = function() {
      _prev();
      const list = document.getElementById('feed-list');
      if (!list) return;
      list.querySelectorAll('.feed-item').forEach(el => {
        if (el.querySelector('.avatar-thumbnail')) return;
        const actor = (el.querySelector('.feed-actor') || {}).textContent || '';
        const name = (actor || '').toLowerCase().trim();
        if (!name) return;
        const rail = el.querySelector('.feed-rail');
        if (rail) {
          const av = document.createElement('span');
          av.innerHTML = _avatarHtml(name, 18);
          av.style.cssText = 'display:block;margin-bottom:3px';
          rail.insertBefore(av, rail.firstChild);
        }
      });
    };
  }

  // Wrap renderSpotlight: substitute "Name" in text with "<avatar>Name".
  if (typeof renderSpotlight === 'function') {
    const _prev = renderSpotlight;
    renderSpotlight = function() {
      _prev();
      const el = document.getElementById('spotlight-text');
      if (!el) return;
      const txt = el.textContent || '';
      const found = (typeof AGENT_NAMES !== 'undefined' ? AGENT_NAMES : []).find(n =>
        new RegExp('\\b' + n.charAt(0).toUpperCase() + n.slice(1) + '\\b').test(txt)
      );
      if (found && !el.querySelector('.avatar-thumbnail')) {
        const av = document.createElement('span');
        av.innerHTML = _avatarHtml(found, 16);
        av.style.cssText = 'display:inline-block;margin-right:6px;vertical-align:middle';
        el.insertBefore(av, el.firstChild);
      }
    };
  }

  // Narration bar: prefix with protagonist avatar.
  if (typeof _pushNarration === 'function') {
    const _prev = _pushNarration;
    window._pushNarration = function(text) {
      _prev(text);
      try {
        const bar = document.getElementById('narration-bar');
        if (!bar) return;
        // Look up cached protagonist if available
        const proto = typeof directorProtagonist !== 'undefined' ? directorProtagonist : null;
        if (!proto) return;
        let av = bar.querySelector('.avatar-thumbnail');
        if (!av) {
          const wrap = document.createElement('span');
          wrap.innerHTML = _avatarHtml(proto, 20);
          wrap.style.cssText = 'flex:0 0 auto;margin-right:8px';
          bar.insertBefore(wrap, bar.firstChild);
          av = bar.querySelector('.avatar-thumbnail');
        } else if (av.dataset.name !== proto) {
          av.src = '/api/agent/' + proto + '/avatar';
          av.dataset.name = proto;
        }
      } catch (e) {}
    };
  }
})();


// ───── Story 10.3: Scene staging modal ─────
const SceneStaging = (function(){
  const PRIORITY = {
    'shared_plan':  100,
    'refusal':      80,
    'disagreement': 78,
    'reconnect':    50,
    'mood_crash':   40,
    'plan_failure': 30,
  };
  const COOLDOWN_MS = 30000;
  const HOLD_MS = 8000;
  let _lastShownAt = 0;
  let _queue = [];
  let _seenEventKeys = new Set();
  let _seenPlans = new Set();
  let _lastTalkAt = {};         // pair-key -> sim_time minute (or wall clock)
  let _lastScene = null;
  let _typingTimer = null;
  let _holdTimer = null;
  let _active = false;

  function _pairKey(a, b) { return a < b ? a + '|' + b : b + '|' + a; }

  function _enqueue(trig) {
    _queue.push(trig);
    _queue.sort((x, y) => (PRIORITY[y.kind]||0) - (PRIORITY[x.kind]||0));
    _maybeShow();
  }

  function _detect() {
    if (!stateData) return;
    // Trigger 1: confirmed shared_plans
    const plans = stateData.shared_plans || [];
    for (const p of plans) {
      if (!p || !p.id || p.status !== 'confirmed') continue;
      if (_seenPlans.has(p.id)) continue;
      _seenPlans.add(p.id);
      const parts = p.participants || [];
      if (parts.length >= 2) {
        _enqueue({
          kind: 'shared_plan',
          a: parts[0], b: parts[1],
          caption: 'A meeting takes shape.',
          dialogue: p.description || ('Plan: ' + (p.id || ''))
        });
      }
    }
    // Trigger 2/3/6: scan event_feed.
    const events = stateData.events || [];
    for (const ev of events) {
      const text = ev.text || '';
      const k = (ev.time || '') + '|' + text;
      if (_seenEventKeys.has(k)) continue;
      _seenEventKeys.add(k);
      const m = text.match(/^([a-z]+)\s/i);
      const actor = m ? m[1].toLowerCase() : null;

      // Refusal: "<actor> declined to <target>: <reason>"
      const refused = text.match(/^([a-z]+)\s+declined to\s+([a-z]+)\b/i);
      if (refused) {
        _enqueue({
          kind: 'refusal',
          a: refused[1].toLowerCase(), b: refused[2].toLowerCase(),
          caption: 'A no spoken aloud.',
          dialogue: text
        });
        continue;
      }
      // Disagreement: "conflict:" tag
      if (/conflict:/i.test(text) && actor) {
        const m2 = text.match(/conflict:\s*([a-z]+)/i);
        const tgt = m2 ? m2[1].toLowerCase() : null;
        _enqueue({
          kind: 'disagreement',
          a: actor, b: tgt || actor,
          caption: 'The room turns sharp.',
          dialogue: text
        });
        continue;
      }
      // Plan failure
      if (/missed plan/i.test(text) && actor) {
        _enqueue({
          kind: 'plan_failure',
          a: actor, b: actor,
          caption: 'A plan slips through.',
          dialogue: text
        });
        continue;
      }
      // First talk_to between pair w/ ≥1 game day quiet
      const said = text.match(/^([a-z]+) says to ([a-z]+):/i);
      if (said) {
        const aA = said[1].toLowerCase(), bB = said[2].toLowerCase();
        const key = _pairKey(aA, bB);
        const now = (stateData.day || 0) * 1440 + (stateData.sim_time || 0);
        const prev = _lastTalkAt[key];
        if (prev !== undefined && (now - prev) >= 1440) {
          _enqueue({
            kind: 'reconnect',
            a: aA, b: bB,
            caption: 'After a long silence.',
            dialogue: text
          });
        }
        _lastTalkAt[key] = now;
      }
    }
    // Trigger 5: mood crash — reuse _prevMood from Round 2
    if (typeof _prevMood !== 'undefined' && stateData.agents) {
      for (const name of Object.keys(stateData.agents)) {
        const ag = stateData.agents[name];
        const m = ag.mood ?? 50;
        const p = _prevMood[name];
        if (p !== undefined && (m - p) <= -15) {
          _enqueue({
            kind: 'mood_crash',
            a: name, b: name,
            caption: 'Something gives way.',
            dialogue: ag.last_action || ''
          });
        }
      }
    }
    // Cap memory growth
    if (_seenEventKeys.size > 1000) {
      _seenEventKeys = new Set(Array.from(_seenEventKeys).slice(-500));
    }
  }

  function _maybeShow() {
    if (_active) return;
    if (!_queue.length) return;
    const now = Date.now();
    if (now - _lastShownAt < COOLDOWN_MS) return;
    const trig = _queue.shift();
    _show(trig);
  }

  function _renderPortraits(trig, hostId) {
    const host = document.getElementById(hostId);
    if (!host) return;
    let html = '';
    if (trig.a && trig.b && trig.a !== trig.b) {
      html = _avatarHtml(trig.a, 96).replace('avatar-thumbnail', 'avatar-thumbnail scene-big')
           + '<span class="scene-vs">·</span>'
           + _avatarHtml(trig.b, 96).replace('avatar-thumbnail', 'avatar-thumbnail scene-big');
    } else if (trig.a) {
      html = _avatarHtml(trig.a, 96).replace('avatar-thumbnail', 'avatar-thumbnail scene-big');
    }
    host.innerHTML = html;
    // Force size on the inserted nodes
    host.querySelectorAll('img,.avatar-thumbnail').forEach(el => {
      el.style.width = '96px'; el.style.height = '96px';
    });
  }

  function _typeOut(el, text) {
    if (_typingTimer) { clearInterval(_typingTimer); _typingTimer = null; }
    if (!el) return;
    el.textContent = '';
    let i = 0;
    const speed = 40;  // ms per char (≈25 cps)
    _typingTimer = setInterval(() => {
      if (i >= text.length) {
        clearInterval(_typingTimer);
        _typingTimer = null;
        return;
      }
      el.textContent += text.charAt(i);
      i++;
    }, speed);
  }

  function _show(trig) {
    _active = true;
    _lastShownAt = Date.now();
    _lastScene = trig;
    const replayBtn = document.getElementById('replay-scene-btn');
    if (replayBtn) replayBtn.disabled = false;
    const modal = document.getElementById('scene-modal');
    if (!modal) { _active = false; return; }
    _renderPortraits(trig, 'scene-portraits');
    const cap = document.getElementById('scene-caption');
    if (cap) cap.textContent = trig.caption || '—';
    const dlg = document.getElementById('scene-dialogue');
    _typeOut(dlg, trig.dialogue || '');
    modal.classList.remove('fading');
    modal.classList.add('visible');
    if (trig.kind === 'refusal' || trig.kind === 'disagreement') Sound.play('sting_r');
    else Sound.play('sting_d');
    if (_holdTimer) clearTimeout(_holdTimer);
    _holdTimer = setTimeout(_dismiss, HOLD_MS);
  }

  function _dismiss() {
    const modal = document.getElementById('scene-modal');
    if (!modal) { _active = false; return; }
    modal.classList.add('fading');
    setTimeout(() => {
      modal.classList.remove('visible');
      modal.classList.remove('fading');
      _active = false;
      _maybeShow();
    }, 400);
    if (_typingTimer) { clearInterval(_typingTimer); _typingTimer = null; }
    if (_holdTimer)   { clearTimeout(_holdTimer); _holdTimer = null; }
  }

  function replay() {
    if (_active || !_lastScene) return;
    _show(_lastScene);
  }

  // wire skip
  (function _wire(){
    const modal = document.getElementById('scene-modal');
    const skip = document.getElementById('scene-skip');
    if (skip) skip.addEventListener('click', _dismiss);
    if (modal) modal.addEventListener('click', e => {
      if (e.target === modal) _dismiss();
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && _active) _dismiss();
    });
    const rb = document.getElementById('replay-scene-btn');
    if (rb) rb.addEventListener('click', replay);
  })();

  return { detect: _detect, replay };
})();


// ───── Story 10.9: End-of-day highlight reel ─────
function renderHighlightReel(day, events) {
  const reel = document.getElementById('highlight-reel');
  if (!reel) return;
  const titleEl = document.getElementById('reel-title');
  const portsEl = document.getElementById('reel-portraits');
  const capEl   = document.getElementById('reel-caption');
  const barEl   = document.getElementById('reel-progress-bar');

  // Score events
  const scored = (events || []).map(ev => {
    const t = ev.text || '';
    let score = 0;
    if (/conflict:/i.test(t)) score = 10;
    else if (/declined plan/i.test(t)) score = 8;
    else if (/declined to/i.test(t)) score = 7;
    else if (/talk_to|says to/i.test(t)) score = 5;
    else if (/moved to/i.test(t)) score = 1;
    return { ev, score };
  }).filter(x => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 5)
    .map(x => x.ev);

  const cards = [];
  cards.push({ title: `Day ${day} — Recap`, ports: [], cap: '', dur: 2000 });
  for (const ev of scored) {
    const t = ev.text || '';
    const m = t.match(/^([a-z]+)\b.*?\b([a-z]+)\b/i);
    const ports = [];
    if (m) {
      const a = m[1].toLowerCase();
      const b = m[2].toLowerCase();
      if ((typeof AGENT_NAMES !== 'undefined' ? AGENT_NAMES : []).includes(a)) ports.push(a);
      if (b !== a && (typeof AGENT_NAMES !== 'undefined' ? AGENT_NAMES : []).includes(b)) ports.push(b);
    }
    let caption = t;
    if (typeof narrativise === 'function') {
      try { caption = narrativise(t) || t; } catch (e) {}
    }
    cards.push({ title: '', ports, cap: caption, dur: 3500 });
  }

  // Cliffhanger fetch is best-effort.
  let cliff = null;
  fetch('/api/cliffhanger/' + (day))
    .then(r => r.ok ? r.json() : null)
    .then(d => { cliff = d && d.text; })
    .catch(()=>{});

  reel.classList.add('visible');
  Sound.play('bell');

  let idx = 0;
  let aborted = false;

  function _renderCard(c) {
    if (titleEl) titleEl.textContent = c.title || '';
    if (capEl)   capEl.textContent   = c.cap   || '';
    if (portsEl) {
      portsEl.innerHTML = (c.ports || []).map(n => _avatarHtml(n, 64)).join('');
    }
    if (barEl) {
      barEl.style.transition = 'none';
      barEl.style.transform  = 'scaleX(0)';
      requestAnimationFrame(() => requestAnimationFrame(() => {
        barEl.style.transition = `transform ${c.dur}ms linear`;
        barEl.style.transform  = 'scaleX(1)';
      }));
    }
  }

  function _step() {
    if (aborted) return;
    if (idx >= cards.length) {
      // Cliffhanger card
      _renderCard({ title: 'Tomorrow…', ports: [], cap: cliff || 'The town turns the page.', dur: 4000 });
      setTimeout(_close, 4000);
      return;
    }
    _renderCard(cards[idx]);
    setTimeout(_step, cards[idx].dur);
    idx++;
  }

  function _close() {
    aborted = true;
    reel.classList.remove('visible');
  }

  function _onKey(e) {
    if (e.key === 'Escape') { _close(); document.removeEventListener('keydown', _onKey); }
  }
  reel.addEventListener('click', _close, { once: true });
  document.addEventListener('keydown', _onKey);

  _step();
}


// ───── Story 10.10: Daily gossip headlines ticker ─────
const GossipTicker = (function(){
  let _headlines = [];
  let _idx = 0;
  let _timer = null;
  let _lastDay = null;

  async function poll() {
    try {
      const d = await fetchJSON('/api/headlines/today');
      const day = (d && d.day) || null;
      const lines = (d && d.headlines) || [];
      if (day !== _lastDay) {
        _lastDay = day;
        _headlines = lines;
        _idx = 0;
        _render();
      } else if (JSON.stringify(lines) !== JSON.stringify(_headlines)) {
        _headlines = lines;
        if (_idx >= _headlines.length) _idx = 0;
        _render();
      }
    } catch (e) {}
  }

  function _render() {
    const wrap = document.getElementById('gossip-ticker');
    const line = document.getElementById('ticker-line');
    if (!wrap || !line) return;
    if (!_headlines.length) {
      wrap.classList.remove('visible');
      if (_timer) { clearTimeout(_timer); _timer = null; }
      return;
    }
    wrap.classList.add('visible');
    _swap();
  }

  function _swap() {
    const line = document.getElementById('ticker-line');
    if (!line) return;
    line.classList.add('leaving');
    setTimeout(() => {
      line.textContent = _headlines[_idx % _headlines.length] || '';
      line.classList.remove('leaving');
      line.classList.add('entering');
      requestAnimationFrame(() => requestAnimationFrame(() => {
        line.classList.remove('entering');
      }));
      _idx = (_idx + 1) % _headlines.length;
      if (_timer) clearTimeout(_timer);
      _timer = setTimeout(_swap, 6000);
    }, 400);
  }

  return { poll };
})();


// ───── Wiring ─────
let _r3PrevDay = null;
let _r3PrevEventCount = 0;
let _r3PrevTalkCount = 0;
let _r3DayEvents = [];
const _r3OrigOnState = onState;
onState = function() {
  _r3OrigOnState.apply(this, arguments);
  if (!stateData) return;

  // Prime avatar cache once
  if (_avatarCache.size === 0 && stateData.agents) {
    _primeAvatarCache(Object.keys(stateData.agents));
  }

  const events = stateData.events || [];

  // UI sound: tick on new event, soft chime on new talk_to
  if (events.length > _r3PrevEventCount) Sound.play('ui_event');
  _r3PrevEventCount = events.length;
  const talkCount = events.filter(e => /says to|talk_to/i.test(e.text || '')).length;
  if (talkCount > _r3PrevTalkCount) Sound.play('ui_msg');
  _r3PrevTalkCount = talkCount;

  // Track per-day events for highlight reel
  for (const ev of events) {
    const k = (ev.time||'') + '|' + (ev.text||'');
    if (!_r3DayEvents.some(e => (e.time||'')+'|'+(e.text||'') === k)) _r3DayEvents.push(ev);
  }

  // Day change → highlight reel (replaces simple recap visually but keeps stats)
  const day = stateData.day ?? 1;
  if (_r3PrevDay === null) _r3PrevDay = day;
  else if (day > _r3PrevDay) {
    renderHighlightReel(_r3PrevDay, _r3DayEvents.slice());
    _r3PrevDay = day;
    _r3DayEvents = [];
  }

  // Detect scene staging triggers
  try { SceneStaging.detect(); } catch (e) {}
};

setInterval(GossipTicker.poll, 30000);
GossipTicker.poll();

// === EPIC10R3_MARK === END
"""


def patch():
    b = ViewerBundle.read(VIEWER)
    t = b.template

    if "EPIC10R3_MARK" in t:
        print("Already patched (EPIC10R3_MARK present); aborting.")
        return False

    # 1) Insert CSS before the Round 2 CSS END (which is just before </style>)
    css_anchor = "/* === EPIC10R2_MARK === END */"
    if css_anchor not in t:
        raise RuntimeError("Round 2 CSS marker missing — viewer not pre-patched.")
    t = t.replace(
        css_anchor,
        css_anchor + "\n" + CSS_BLOCK,
        1,
    )

    # 2) Insert HUD buttons in the masthead-right block, after director-toggle.
    hud_anchor = '<button id="director-toggle" class="active" title="Toggle director mode"><span id="dirmode-glyph">🎬</span></button>'
    if hud_anchor not in t:
        raise RuntimeError("Director toggle anchor missing — Round 2 HUD changed.")
    t = t.replace(hud_anchor, hud_anchor + "\n      " + HUD_BUTTON_HTML, 1)

    # 3) Insert gossip ticker just below the masthead (before #substrip).
    sub_anchor = '<!-- ───────────── SUB-STRIP: clock / timeline / counters ───────────── -->'
    if sub_anchor not in t:
        raise RuntimeError("Substrip anchor missing.")
    t = t.replace(sub_anchor, GOSSIP_TICKER_HTML + "\n  " + sub_anchor, 1)

    # 4) Insert scene modal + reel + audio popover just before </body>.
    body_anchor = "</body>"
    if t.count(body_anchor) < 1:
        raise RuntimeError("</body> missing.")
    t = t.replace(body_anchor, SCENE_MODAL_HTML + "\n" + body_anchor, 1)

    # 5) Insert JS just before the end of the IIFE wrapper.
    js_anchor = "// === EPIC10R2_MARK === END\n\n})();"
    if js_anchor not in t:
        raise RuntimeError("Round 2 JS END anchor not found.")
    t = t.replace(js_anchor, "// === EPIC10R2_MARK === END\n" + JS_BLOCK + "\n})();", 1)

    b.template = t
    b.write(VIEWER)
    print(f"Patched viewer.html: template now {len(b.template):,} chars")
    return True


if __name__ == "__main__":
    patch()

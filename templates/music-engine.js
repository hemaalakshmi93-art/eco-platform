/**
 * music-engine.js
 * Drop this <script src="music-engine.js"></script> into every page.
 * It reads/writes the same localStorage key your settings page uses,
 * so the toggle in Settings is always in sync.
 *
 * HOW IT WORKS:
 *  - On page load it checks if music is enabled in settings (S.music = true).
 *  - Because autoplay is blocked by browsers, we show a small floating
 *    "click anywhere to start music" banner on the FIRST visit of a session.
 *  - After the first user interaction, audio is unlocked and music starts.
 *  - A floating mini-player bar appears at the bottom-left on every page.
 *  - Navigating to another page: music state is stored in sessionStorage
 *    so the engine knows audio was already unlocked this session.
 */

(function () {
  'use strict';

  /* ── CONSTANTS ─────────────────────────────────────────────────────── */
  const STORAGE_KEY   = 'app_s4';          // same key as settings page
  const SESSION_KEY   = 'zephyra_audio_ok'; // tracks unlock within tab session
  const DEFAULTS = {
    dark: false, accent: '#4CAF50', fontSize: 'medium', compact: false,
    sound: true, music: true,               // music ON by default
    musicTheme: 'lofi', notif: true, email: false,
    lang: 'en', date: 'dmy', timeFormat: '12'
  };

  /* ── STATE ──────────────────────────────────────────────────────────── */
  let S            = { ...DEFAULTS };
  let audioCtx     = null;
  let audioUnlocked = false;
  let musicPlaying  = false;
  let masterGain    = null;
  let stoppers      = [];          // fns to call when stopping current theme
  let fadeTimer     = null;

  /* ── LOAD SETTINGS ──────────────────────────────────────────────────── */
  function loadSettings() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) S = { ...DEFAULTS, ...JSON.parse(raw) };
    } catch (e) { S = { ...DEFAULTS }; }
  }

  function saveSettings() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(S)); } catch (e) {}
  }

  /* ── AUDIO CONTEXT ──────────────────────────────────────────────────── */
  async function unlockAudio() {
    if (audioUnlocked) return true;
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      if (audioCtx.state === 'suspended') await audioCtx.resume();
      // silent buffer trick
      const buf = audioCtx.createBuffer(1, 1, 22050);
      const src = audioCtx.createBufferSource();
      src.buffer = buf; src.connect(audioCtx.destination); src.start(0);
      audioUnlocked = true;
      sessionStorage.setItem(SESSION_KEY, '1');
      return true;
    } catch (e) { return false; }
  }

  async function ensureCtx() {
    if (!audioUnlocked) return false;
    if (audioCtx && audioCtx.state === 'suspended') await audioCtx.resume();
    return !!audioCtx;
  }

  /* ── MUSIC STOP ─────────────────────────────────────────────────────── */
  function stopMusic(fadeDuration = 1.2) {
    if (!masterGain) { _hardStop(); return; }
    const g = masterGain;
    try {
      g.gain.setTargetAtTime(0, audioCtx.currentTime, fadeDuration / 4);
    } catch (e) {}
    fadeTimer = setTimeout(() => {
      _hardStop();
      updateUI(false);
    }, fadeDuration * 1000 + 200);
  }

  function _hardStop() {
    clearTimeout(fadeTimer);
    stoppers.forEach(fn => { try { fn(); } catch (e) {} });
    stoppers = [];
    if (masterGain) { try { masterGain.disconnect(); } catch (e) {} masterGain = null; }
    musicPlaying = false;
  }

  /* ── MUSIC START ─────────────────────────────────────────────────────── */
  async function startMusic(theme) {
    _hardStop();
    if (!await ensureCtx()) return;

    masterGain = audioCtx.createGain();
    masterGain.gain.setValueAtTime(0, audioCtx.currentTime);
    masterGain.gain.setTargetAtTime(0.28, audioCtx.currentTime, 0.8);
    masterGain.connect(audioCtx.destination);
    musicPlaying = true;

    if (theme === 'lofi')     playLofi(masterGain);
    else if (theme === 'ambient') playAmbient(masterGain);
    else                          playUpbeat(masterGain);

    updateUI(true, theme);
  }

  /* ── OSC HELPERS ────────────────────────────────────────────────────── */
  function osc(type, freq, gainVal, dur, startAt, dest) {
    if (!musicPlaying) return;
    try {
      const o = audioCtx.createOscillator();
      const g = audioCtx.createGain();
      const t = audioCtx.currentTime + (startAt || 0);
      o.type = type;
      o.frequency.setValueAtTime(freq, t);
      g.gain.setValueAtTime(gainVal, t);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      o.connect(g); g.connect(dest || masterGain);
      o.start(t); o.stop(t + dur + 0.05);
    } catch (e) {}
  }

  function schedLoop(fn, ms) {
    let tid;
    function loop() { if (!musicPlaying) return; fn(); tid = setTimeout(loop, ms); }
    loop();
    stoppers.push(() => clearTimeout(tid));
  }

  /* ── LO-FI THEME ────────────────────────────────────────────────────── */
  // Warm jazzy chord progression: Cmaj7 → Am7 → Fmaj7 → G7
  function playLofi(dest) {
    const progressions = [
      [261.63, 329.63, 392.00, 493.88],  // Cmaj7
      [220.00, 261.63, 329.63, 415.30],  // Am7
      [174.61, 220.00, 261.63, 349.23],  // Fmaj7
      [196.00, 246.94, 293.66, 392.00],  // G7
    ];
    let beat = 0;

    function step() {
      const chord = progressions[beat % progressions.length];
      // Soft pad
      chord.forEach((f, i) => {
        osc('triangle', f * 0.5, 0.038, 2.4, i * 0.02, dest);
      });
      // Bass note
      osc('sine', chord[0] * 0.25, 0.07, 2.0, 0, dest);

      // Hi-hat
      if (beat % 2 === 1) {
        try {
          const buf = audioCtx.createBuffer(1, audioCtx.sampleRate * 0.05, audioCtx.sampleRate);
          const data = buf.getChannelData(0);
          for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * 0.03;
          const src = audioCtx.createBufferSource();
          const filt = audioCtx.createBiquadFilter();
          const g = audioCtx.createGain();
          filt.type = 'highpass'; filt.frequency.value = 8000;
          src.buffer = buf;
          src.connect(filt); filt.connect(g); g.connect(dest);
          g.gain.setValueAtTime(0.4, audioCtx.currentTime);
          g.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + 0.05);
          src.start();
        } catch (e) {}
      }
      beat++;
    }
    schedLoop(step, 2000);
  }

  /* ── AMBIENT THEME ──────────────────────────────────────────────────── */
  // Slow evolving drone pads — nature / meditation feel
  function playAmbient(dest) {
    const freqs = [110, 138.59, 164.81, 220, 261.63, 329.63];
    const oscs  = [];
    const lfos  = [];

    freqs.forEach((f, i) => {
      try {
        const o  = audioCtx.createOscillator();
        const g  = audioCtx.createGain();
        const lf = audioCtx.createOscillator();
        const lg = audioCtx.createGain();

        o.type = i % 2 === 0 ? 'sine' : 'triangle';
        o.frequency.setValueAtTime(f, audioCtx.currentTime);
        lf.type = 'sine';
        lf.frequency.setValueAtTime(0.03 + i * 0.015, audioCtx.currentTime);
        lg.gain.setValueAtTime(f * 0.004, audioCtx.currentTime);

        lf.connect(lg); lg.connect(o.frequency);
        g.gain.setValueAtTime(0.025 - i * 0.002, audioCtx.currentTime);
        o.connect(g); g.connect(dest);

        lf.start(); o.start();
        oscs.push(o); lfos.push(lf);
      } catch (e) {}
    });

    // Slowly evolving chord swells every 8 s
    let swellBeat = 0;
    const swellChords = [
      [261.63, 329.63, 392.00],
      [220.00, 277.18, 329.63],
      [196.00, 246.94, 293.66],
    ];
    function swell() {
      swellChords[swellBeat % swellChords.length].forEach((f, i) => {
        try {
          const o = audioCtx.createOscillator();
          const g = audioCtx.createGain();
          const t = audioCtx.currentTime;
          o.type = 'sine';
          o.frequency.setValueAtTime(f, t);
          g.gain.setValueAtTime(0, t);
          g.gain.linearRampToValueAtTime(0.04, t + 3);
          g.gain.linearRampToValueAtTime(0, t + 7.5);
          o.connect(g); g.connect(dest);
          o.start(t); o.stop(t + 8);
        } catch (e) {}
      });
      swellBeat++;
    }
    swell();
    schedLoop(swell, 8000);

    stoppers.push(() => {
      oscs.forEach(o => { try { o.stop(); o.disconnect(); } catch (e) {} });
      lfos.forEach(l => { try { l.stop(); l.disconnect(); } catch (e) {} });
    });
  }

  /* ── UPBEAT THEME ───────────────────────────────────────────────────── */
  // C-major pentatonic melody with kick + snare groove
  function playUpbeat(dest) {
    const penta    = [261.63, 293.66, 329.63, 392.00, 440.00, 523.25, 587.33];
    const melody   = [0, 2, 4, 6, 4, 2, 4, 5, 4, 2, 0, 2];
    let step = 0;

    function tick() {
      const freq = penta[melody[step % melody.length]];
      osc('square', freq, 0.038, 0.17, 0, dest);

      // Kick on beat 1 & 3
      if (step % 4 === 0 || step % 4 === 2) {
        try {
          const k = audioCtx.createOscillator();
          const kg = audioCtx.createGain();
          const t = audioCtx.currentTime;
          k.type = 'sine';
          k.frequency.setValueAtTime(160, t);
          k.frequency.exponentialRampToValueAtTime(38, t + 0.14);
          kg.gain.setValueAtTime(0.12, t);
          kg.gain.exponentialRampToValueAtTime(0.0001, t + 0.16);
          k.connect(kg); kg.connect(dest);
          k.start(t); k.stop(t + 0.18);
        } catch (e) {}
      }

      // Snare on beat 2 & 4
      if (step % 4 === 1 || step % 4 === 3) {
        try {
          const buf = audioCtx.createBuffer(1, audioCtx.sampleRate * 0.12, audioCtx.sampleRate);
          const d   = buf.getChannelData(0);
          for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * 0.08;
          const s = audioCtx.createBufferSource();
          const g = audioCtx.createGain();
          const t = audioCtx.currentTime;
          s.buffer = buf;
          g.gain.setValueAtTime(0.5, t);
          g.gain.exponentialRampToValueAtTime(0.0001, t + 0.12);
          s.connect(g); g.connect(dest);
          s.start(t);
        } catch (e) {}
      }

      step++;
    }
    schedLoop(tick, 215);
  }

  /* ── MINI PLAYER UI ─────────────────────────────────────────────────── */
  const THEME_LABELS = { lofi: 'Lo-fi Chill', ambient: 'Ambient', upbeat: 'Upbeat' };
  const THEME_ICONS  = { lofi: '🎷', ambient: '🌊', upbeat: '🥁' };

  function buildPlayer() {
    if (document.getElementById('zephyra-music-player')) return;

    const style = document.createElement('style');
    style.textContent = `
      #zephyra-music-player {
        position: fixed; bottom: 20px; left: 20px; z-index: 99999;
        display: flex; align-items: center; gap: 10px;
        background: rgba(7,17,31,0.88);
        backdrop-filter: blur(18px);
        border: 1px solid rgba(34,211,238,0.18);
        border-radius: 40px; padding: 8px 16px 8px 10px;
        font-family: 'DM Sans', 'Segoe UI', sans-serif;
        box-shadow: 0 8px 32px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,255,255,0.04);
        transition: opacity .3s, transform .3s;
        min-width: 200px;
        animation: zmp-slide-in .4s cubic-bezier(.4,0,.2,1);
      }
      @keyframes zmp-slide-in {
        from { opacity:0; transform: translateY(20px); }
        to   { opacity:1; transform: translateY(0); }
      }
      #zephyra-music-player.hidden { opacity:0; pointer-events:none; transform:translateY(20px); }

      #zmp-toggle {
        width: 34px; height: 34px; border-radius: 50%; border: none; cursor: pointer;
        background: linear-gradient(135deg, #22d3ee, #8b5cf6);
        display: flex; align-items: center; justify-content: center;
        flex-shrink: 0; font-size: 15px;
        box-shadow: 0 2px 10px rgba(34,211,238,0.35);
        transition: transform .2s, box-shadow .2s;
      }
      #zmp-toggle:hover { transform: scale(1.1); box-shadow: 0 4px 16px rgba(34,211,238,0.5); }

      #zmp-bars {
        display: flex; align-items: flex-end; gap: 2px; height: 18px; width: 20px;
      }
      #zmp-bars span {
        width: 3px; background: linear-gradient(to top, #22d3ee, #8b5cf6);
        border-radius: 2px; animation: zmp-bar .65s ease-in-out infinite alternate;
      }
      #zmp-bars span:nth-child(1){height:5px;animation-delay:0s}
      #zmp-bars span:nth-child(2){height:14px;animation-delay:.12s}
      #zmp-bars span:nth-child(3){height:8px;animation-delay:.24s}
      #zmp-bars span:nth-child(4){height:16px;animation-delay:.08s}
      #zmp-bars.paused span { animation-play-state: paused; height: 4px !important; }
      @keyframes zmp-bar { from{transform:scaleY(.3)} to{transform:scaleY(1)} }

      #zmp-info { flex: 1; min-width: 0; }
      #zmp-title {
        font-size: 12px; font-weight: 600; color: #eef6ff;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      #zmp-theme {
        font-size: 10px; color: #64748b; margin-top: 1px;
      }

      #zmp-skip {
        background: none; border: none; cursor: pointer; color: #64748b;
        font-size: 16px; padding: 0 2px; transition: color .2s; flex-shrink: 0;
        line-height: 1;
      }
      #zmp-skip:hover { color: #22d3ee; }

      /* Unlock banner */
      #zmp-banner {
        position: fixed; bottom: 20px; left: 20px; z-index: 99999;
        display: flex; align-items: center; gap: 10px;
        background: rgba(7,17,31,0.92); backdrop-filter: blur(18px);
        border: 1px solid rgba(34,211,238,0.25); border-radius: 14px;
        padding: 12px 18px; font-family: 'DM Sans','Segoe UI',sans-serif;
        box-shadow: 0 8px 32px rgba(0,0,0,0.45);
        animation: zmp-slide-in .4s cubic-bezier(.4,0,.2,1);
        max-width: 300px;
      }
      #zmp-banner.hidden { display: none; }
      #zmp-banner-text { font-size: 12px; color: #94a3b8; }
      #zmp-banner-text strong { color: #eef6ff; display: block; margin-bottom: 2px; }
      #zmp-banner-btn {
        flex-shrink: 0; background: linear-gradient(135deg, #22d3ee, #8b5cf6);
        border: none; border-radius: 8px; color: #fff; font-weight: 700;
        font-size: 12px; padding: 7px 14px; cursor: pointer; white-space: nowrap;
        font-family: 'DM Sans','Segoe UI',sans-serif; transition: opacity .2s;
      }
      #zmp-banner-btn:hover { opacity: .85; }
    `;
    document.head.appendChild(style);

    // Unlock banner
    const banner = document.createElement('div');
    banner.id = 'zmp-banner';
    banner.innerHTML = `
      <div id="zmp-banner-text">
        <strong>🎵 Background music ready</strong>
        Tap to start your Zephyra soundtrack
      </div>
      <button id="zmp-banner-btn">▶ Play</button>
    `;
    document.body.appendChild(banner);

    // Mini player (hidden until audio unlocked)
    const player = document.createElement('div');
    player.id = 'zephyra-music-player';
    player.classList.add('hidden');
    player.innerHTML = `
      <button id="zmp-toggle" title="Play/Pause">⏸</button>
      <div id="zmp-bars"><span></span><span></span><span></span><span></span></div>
      <div id="zmp-info">
        <div id="zmp-title">Loading…</div>
        <div id="zmp-theme"></div>
      </div>
      <button id="zmp-skip" title="Next theme">⏭</button>
    `;
    document.body.appendChild(player);

    // Events
    document.getElementById('zmp-banner-btn').addEventListener('click', handleUnlockClick);
    document.getElementById('zmp-toggle').addEventListener('click', handleToggle);
    document.getElementById('zmp-skip').addEventListener('click', handleSkip);
  }

  async function handleUnlockClick() {
    const ok = await unlockAudio();
    if (!ok) return;
    document.getElementById('zmp-banner')?.classList.add('hidden');
    document.getElementById('zephyra-music-player')?.classList.remove('hidden');
    if (S.music) await startMusic(S.musicTheme);
    else updateUI(false);
  }

  async function handleToggle() {
    if (!audioUnlocked) { await handleUnlockClick(); return; }
    S.music = !S.music;
    saveSettings();
    if (S.music) await startMusic(S.musicTheme);
    else stopMusic();
    updateUI(S.music);
  }

  const THEMES = ['lofi', 'ambient', 'upbeat'];
  async function handleSkip() {
    const idx = THEMES.indexOf(S.musicTheme);
    S.musicTheme = THEMES[(idx + 1) % THEMES.length];
    saveSettings();
    if (S.music && audioUnlocked) await startMusic(S.musicTheme);
    updateUI(S.music);
  }

  function updateUI(playing, theme) {
    const t = theme || S.musicTheme;
    const bars   = document.getElementById('zmp-bars');
    const toggle = document.getElementById('zmp-toggle');
    const title  = document.getElementById('zmp-title');
    const sub    = document.getElementById('zmp-theme');
    if (bars)   bars.classList.toggle('paused', !playing);
    if (toggle) toggle.textContent = playing ? '⏸' : '▶';
    if (title)  title.textContent = `${THEME_ICONS[t]} ${THEME_LABELS[t]}`;
    if (sub)    sub.textContent   = playing ? 'Now playing' : 'Paused';
  }

  /* ── BOOT ───────────────────────────────────────────────────────────── */
  async function boot() {
    loadSettings();

    // If music is disabled in settings, don't show anything
    if (!S.music) return;

    buildPlayer();

    // If audio was already unlocked in this browser session, start right away
    if (sessionStorage.getItem(SESSION_KEY) === '1') {
      const ok = await unlockAudio();
      if (ok) {
        document.getElementById('zmp-banner')?.classList.add('hidden');
        document.getElementById('zephyra-music-player')?.classList.remove('hidden');
        await startMusic(S.musicTheme);
      }
    }
    // Otherwise the banner stays visible, waiting for user click
  }

  // Wait for DOM
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  /* ── PUBLIC API ─────────────────────────────────────────────────────── */
  // The settings page can call these to stay in sync:
  window.ZephyraMusic = {
    start:   startMusic,
    stop:    stopMusic,
    unlock:  unlockAudio,
    isPlaying: () => musicPlaying,
    setTheme: async (t) => { S.musicTheme = t; if (musicPlaying) await startMusic(t); },
    getState: () => ({ ...S }),
  };

})();
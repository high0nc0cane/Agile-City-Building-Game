// music.js - shared background music, persists across page loads.
// All game modes share the same in-game track; menu and instructions share
// the menu track. Tracks fade in gently to avoid abrupt audio jumps.
(function () {
  const MENU_TRACK = '/static/music/SOURCE OSTSuper Nintendo World_ World 1 - Super Mario 3D World.mp3';
  const GAME_TRACK = '/static/music/super_mario_galaxy_2_puzzle_plank.mp3';
  const TRACK_SETTINGS = {
    [MENU_TRACK]: { volume: 0.34 },
    [GAME_TRACK]: { volume: 0.34 },
  };
  const DEFAULT_VOLUME = 0.34;
  const FADE_IN_MS = 700;
  const FADE_OUT_MS = 180;
  const FADE_STEP_MS = 40;

  const audio = new Audio();
  audio.loop = true;
  audio.preload = 'auto';
  audio.volume = 0;

  let currentSrc = null;
  let currentTargetVolume = DEFAULT_VOLUME;
  let bootstrapped = false;
  let fadeTimer = null;
  let leavingPage = false;

  function timeKey(src) {
    return `music_time:${src}`;
  }

  function getTargetVolume(src) {
    return TRACK_SETTINGS[src]?.volume ?? DEFAULT_VOLUME;
  }

  function stopFade() {
    if (fadeTimer) {
      clearInterval(fadeTimer);
      fadeTimer = null;
    }
  }

  function fadeTo(targetVolume, duration) {
    stopFade();

    if (audio.muted) {
      audio.volume = targetVolume;
      return;
    }

    const startVolume = audio.volume;
    const delta = targetVolume - startVolume;
    if (Math.abs(delta) < 0.01 || duration <= 0) {
      audio.volume = targetVolume;
      return;
    }

    const steps = Math.max(1, Math.round(duration / FADE_STEP_MS));
    let step = 0;

    fadeTimer = setInterval(() => {
      step += 1;
      audio.volume = startVolume + (delta * step) / steps;
      if (step >= steps) {
        audio.volume = targetVolume;
        stopFade();
      }
    }, FADE_STEP_MS);
  }

  function applySavedState(src) {
    const muted = sessionStorage.getItem('music_muted') === 'true';
    audio.muted = muted;

    const savedTime = parseFloat(sessionStorage.getItem(timeKey(src)) || '0');
    if (savedTime > 0) {
      const restoreTime = () => {
        try {
          audio.currentTime = savedTime;
        } catch (error) {
          // Ignore invalid restore times.
        }
      };

      if (audio.readyState >= 1) {
        restoreTime();
      } else {
        audio.addEventListener('loadedmetadata', restoreTime, { once: true });
      }
    }
  }

  function persistTime() {
    if (currentSrc) {
      sessionStorage.setItem(timeKey(currentSrc), String(audio.currentTime));
    }
  }

  function tryPlay() {
    audio.play().catch(() => {
      // Autoplay can be blocked until the first user gesture.
    });
  }

  function updateMuteButton() {
    if (!window.musicToggleButton) return;
    window.musicToggleButton.textContent = audio.muted ? '🔇' : '🔊';
  }

  function setTrack(src) {
    if (!src) {
      return;
    }

    currentTargetVolume = getTargetVolume(src);

    if (src === currentSrc) {
      if (!bootstrapped) {
        bootstrapped = true;
        tryPlay();
      }
      fadeTo(currentTargetVolume, FADE_IN_MS);
      return;
    }

    persistTime();
    currentSrc = src;
    audio.volume = 0;
    audio.src = src;
    applySavedState(src);
    audio.load();

    if (!bootstrapped) {
      bootstrapped = true;
    }
    tryPlay();
    fadeTo(currentTargetVolume, FADE_IN_MS);
  }

  function resolveTrack() {
    // Hao Ying: choose the page-appropriate background music so menus and
    // gameplay each feel more engaging with their own looping track.
    if (document.querySelector('.game-body')) {
      setTrack(GAME_TRACK);
      return;
    }

    setTrack(MENU_TRACK);
  }

  function fadeOutForNavigation(callback) {
    if (leavingPage) {
      return;
    }
    leavingPage = true;
    persistTime();

    if (audio.muted || audio.paused || audio.volume <= 0.01) {
      callback();
      return;
    }

    fadeTo(0, FADE_OUT_MS);
    window.setTimeout(callback, FADE_OUT_MS);
  }

  function handleInternalLinkClick(event) {
    const anchor = event.target.closest('a[href]');
    if (!anchor) {
      return;
    }

    const href = anchor.getAttribute('href');
    if (!href || href.startsWith('#') || anchor.target === '_blank') {
      return;
    }

    const url = new URL(anchor.href, window.location.href);
    if (url.origin !== window.location.origin) {
      return;
    }

    event.preventDefault();
    fadeOutForNavigation(() => {
      window.location.href = url.href;
    });
  }

  // Most browsers require a user gesture before audio can play with sound.
  ['click', 'keydown', 'touchstart'].forEach((evt) => {
    document.addEventListener(evt, function onFirstInteract() {
      tryPlay();
      if (!audio.muted) {
        fadeTo(currentTargetVolume, 220);
      }
      document.removeEventListener(evt, onFirstInteract);
    }, { once: true });
  });

  setInterval(persistTime, 1000);
  window.addEventListener('beforeunload', persistTime);
  window.addEventListener('pagehide', persistTime);

  // --- Mute button (fixed corner, same on every page) ---
  const btn = document.createElement('button');
  btn.id = 'music-toggle-btn';
  btn.setAttribute('aria-label', 'Toggle music');
  window.musicToggleButton = btn;
  updateMuteButton();
  Object.assign(btn.style, {
    position: 'fixed',
    bottom: '16px',
    right: '16px',
    zIndex: '9999',
    width: '44px',
    height: '44px',
    borderRadius: '50%',
    border: 'none',
    background: 'rgba(0,0,0,0.55)',
    color: '#fff',
    fontSize: '20px',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  });
  btn.addEventListener('click', (event) => {
    event.stopPropagation();
    audio.muted = !audio.muted;
    sessionStorage.setItem('music_muted', String(audio.muted));
    updateMuteButton();
    if (!audio.muted) {
      tryPlay();
      fadeTo(currentTargetVolume, 220);
    }
  });

  document.addEventListener('DOMContentLoaded', () => {
    document.body.appendChild(btn);
    document.addEventListener('click', handleInternalLinkClick, true);
    resolveTrack();
  });

  window.addEventListener('music:navigate', (event) => {
    const destination = event.detail?.href;
    if (!destination) {
      return;
    }

    fadeOutForNavigation(() => {
      window.location.href = destination;
    });
  });
})();

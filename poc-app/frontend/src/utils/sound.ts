// Synthesized alert tones via the Web Audio API - no external audio file,
// so there's nothing to fetch/host/license. Best-effort only: browsers
// that don't support AudioContext (or that block autoplay-without-gesture)
// just silently get no sound, never a broken UI.

export function playRecaptureBuzzer() {
  try {
    const AudioContextCtor = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextCtor) return;
    const ctx = new AudioContextCtor();
    const now = ctx.currentTime;

    // Forklift/truck reversing-beeper pattern - flat, evenly-spaced,
    // piercing square-wave beeps at one fixed pitch. Recognizable
    // warehouse-floor "pay attention" sound, on-brand for a warehouse
    // scanning app - deliberately not a phone/UI chime.
    function beep(startOffset: number, duration: number) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "square";
      osc.frequency.setValueAtTime(1000, now + startOffset);
      const end = now + startOffset + duration;
      gain.gain.setValueAtTime(0, now + startOffset);
      gain.gain.linearRampToValueAtTime(0.22, now + startOffset + 0.008);
      gain.gain.setValueAtTime(0.22, end - 0.015);
      gain.gain.linearRampToValueAtTime(0, end);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now + startOffset);
      osc.stop(end + 0.02);
    }

    const beepLen = 0.15;
    const gap = 0.15;
    for (let i = 0; i < 4; i++) {
      beep(i * (beepLen + gap), beepLen);
    }

    setTimeout(() => { ctx.close().catch(() => {}); }, (4 * 0.3 + 0.3) * 1000);
  } catch {
    // Audio is a nice-to-have here, never worth breaking the rejection
    // popup itself over.
  }
}

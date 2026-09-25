// Generates a royalty-free ambient music bed (public/music/bed.mp3): pad + arpeggio + sub + soft kick.
// Run: node scripts/make-music.mjs && ffmpeg -y -i public/music/bed.wav -b:a 192k public/music/bed.mp3 && rm public/music/bed.wav
import { writeFileSync } from "node:fs";

const SR = 44100;
const SECONDS = 92;
const BPM = 100;
const beat = 60 / BPM;
const chordLen = beat * 8;
const n = Math.floor(SR * SECONDS);
const out = new Float32Array(n * 2);

const hz = (midi) => 440 * Math.pow(2, (midi - 69) / 12);
// vi – IV – I – V in C major
const chords = [
  [57, 60, 64], // Am
  [53, 57, 60], // F
  [48, 52, 55], // C
  [55, 59, 62], // G
];
const arpPattern = [0, 1, 2, 1, 2, 0, 1, 2];

let rng = 7;
const rand = () => ((rng = (rng * 16807) % 2147483647) / 2147483647);

for (let i = 0; i < n; i++) {
  const t = i / SR;
  const ci = Math.floor(t / chordLen);
  const tc = t - ci * chordLen;
  const chord = chords[ci % chords.length];
  const prev = chords[(ci + chords.length - 1) % chords.length];
  const xf = Math.min(1, tc / 0.9);

  // pad: detuned sines, crossfaded between chords
  let pad = 0;
  for (const [notes, g] of [[chord, xf], [prev, 1 - xf]]) {
    if (g <= 0) continue;
    for (const m of notes) {
      const f = hz(m);
      pad += g * (Math.sin(2 * Math.PI * f * 1.003 * t) + Math.sin(2 * Math.PI * f * 0.997 * t) + 0.3 * Math.sin(2 * Math.PI * f * 2 * t));
    }
  }
  pad *= 0.028 * (0.85 + 0.15 * Math.sin(2 * Math.PI * 0.2 * t));

  // sub bass on the chord root
  const sub = 0.07 * Math.sin(2 * Math.PI * hz(chord[0] - 24) * t) * Math.min(1, tc / 0.2);

  // arpeggio in 8ths, joins after the intro
  const eighth = beat / 2;
  const ei = Math.floor(t / eighth);
  const te = t - ei * eighth;
  const note = chord[arpPattern[ei % 8]] + 12;
  const env = Math.exp(-te / 0.16) * Math.min(1, te / 0.004);
  const arpGain = Math.min(1, Math.max(0, (t - 5) / 3)) * (t > 84 ? Math.max(0, (88 - t) / 4) : 1);
  const f = hz(note);
  const arp = arpGain * 0.06 * env * (Math.sin(2 * Math.PI * f * t) + 0.25 * Math.sin(2 * Math.PI * f * 3 * t));

  // soft kick on beats 1 and 3, joins at ~6s
  const bi = Math.floor(t / beat);
  const tb = t - bi * beat;
  const kickOn = t > 6 && t < 86 && bi % 2 === 0;
  const kick = kickOn ? 0.16 * Math.exp(-tb / 0.12) * Math.sin(2 * Math.PI * (48 + 90 * Math.exp(-tb / 0.03)) * tb) : 0;

  // airy hat on the offbeat
  const hat = t > 14 && t < 86 && tb > beat / 2 && tb < beat / 2 + 0.05 ? 0.012 * (rand() * 2 - 1) * Math.exp(-(tb - beat / 2) / 0.015) : 0;

  const master = Math.min(1, t / 2.5) * Math.min(1, (SECONDS - t) / 4);
  const l = Math.tanh((pad + sub + arp * 1.1 + kick + hat) * 1.2) * master;
  const r = Math.tanh((pad + sub + arp * 0.9 + kick + hat) * 1.2) * master;
  out[i * 2] = l;
  out[i * 2 + 1] = r;
}

const buf = Buffer.alloc(44 + n * 4);
buf.write("RIFF", 0); buf.writeUInt32LE(36 + n * 4, 4); buf.write("WAVE", 8);
buf.write("fmt ", 12); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(2, 22);
buf.writeUInt32LE(SR, 24); buf.writeUInt32LE(SR * 4, 28); buf.writeUInt16LE(4, 32); buf.writeUInt16LE(16, 34);
buf.write("data", 36); buf.writeUInt32LE(n * 4, 40);
for (let i = 0; i < n * 2; i++) buf.writeInt16LE(Math.round(Math.max(-1, Math.min(1, out[i])) * 32000), 44 + i * 2);
writeFileSync(new URL("../public/music/bed.wav", import.meta.url), buf);
console.log("wrote public/music/bed.wav");

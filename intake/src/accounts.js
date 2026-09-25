import catalog from './catalog.json';

const palettes = [
  ['#302c85', '#b58cf0', '#ffd6ac'],
  ['#145e75', '#58cfbd', '#e6f3a4'],
  ['#5b2677', '#e98ba2', '#ffe2ae'],
  ['#234ea0', '#64b8ed', '#c7f2de'],
  ['#7c3549', '#e49462', '#f9e5a0'],
  ['#354477', '#9997e8', '#f5bddc'],
  ['#23655b', '#9ac87e', '#f6e8b6'],
  ['#843957', '#e278ad', '#e6c5ff'],
  ['#365b8c', '#7dd1c8', '#fce0b7'],
  ['#743d94', '#be89ea', '#bde1ff'],
  ['#88612a', '#edb75f', '#f7ead0'],
  ['#4a487b', '#bd8faa', '#f4c9a8'],
].map(palette => palette.map(hex => [1, 3, 5].map(offset => parseInt(hex.slice(offset, offset + 2), 16))));

function hash(value) {
  return Array.from(value).reduce((seed, letter) => Math.imul(seed ^ letter.charCodeAt(0), 16777619) >>> 0, 2166136261);
}

function createAvatar(id, colorway) {
  const seed = hash(id);
  const palette = palettes[colorway % palettes.length];
  return Array.from({ length: 64 }, (_, index) => {
    const x = index % 8;
    const y = Math.floor(index / 8);
    const noise = (hash(`${seed}:${index}`) % 100) / 100;
    const wave = Math.sin((x + (seed % 7)) * .7 + y * .45) * .12;
    const tone = Math.max(0, Math.min(1, (x * .6 + y * .4) / 7 + wave + (noise - .5) * .22));
    const position = Math.round(tone * 10) / 5;
    const start = Math.min(1, Math.floor(position));
    const mix = position - start;
    const color = palette[start].map((channel, i) => Math.round(channel + (palette[start + 1][i] - channel) * mix));
    return { x, y, color: `rgb(${color.join(',')})`, delay: (x + y) * 13 + Math.round(noise * 35) };
  });
}


// Display names drawn from the sample ticket reporters and team assignees.
const accountNames = {
  "client": "Luca Rinaldi",
  "Client Services": "Carlos Ortiz",
  "Enterprise Applications": "David Kim",
  "Investment Operations": "Vicky Chen",
  "Market Data Services": "Gina Muller",
  "Risk & Controls": "Maya Kerr",
  "Securities Operations": "Nora Leclerc",
  "Service Desk": "Leo Zimmer",
  "Tax & Reporting": "William Maier",
  "Trading Support": "Adam Paul",
  "Treasury & Cash": "Oliver Varga",
  "Valuation & Pricing": "Irina Sokolov"
};

export const accounts = [
  { id: 'client', label: 'Client' },
  ...catalog['Service Team(s)'].map(team => ({ id: team, label: team })),
].map((account, index) => ({ ...account, name: accountNames[account.id], avatar: createAvatar(account.id, index) }));

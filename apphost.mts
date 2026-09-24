// Aspire TypeScript AppHost — runs the triage backend (FastAPI/uv) and the React frontend (Vite) locally.
// Start with: aspire run
import { existsSync, readFileSync } from 'node:fs';
import { createBuilder } from './.aspire/modules/aspire.mjs';

// backend/.env (gitignored) is the single place for local settings, shared with standalone `uvicorn` runs.
const dotenv: Record<string, string> = existsSync('./backend/.env')
    ? Object.fromEntries(
          readFileSync('./backend/.env', 'utf8')
              .split('\n')
              .map((line) => line.match(/^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$/))
              .filter((m): m is RegExpMatchArray => m !== null && m[2] !== '')
              .map((m) => [m[1], m[2]]),
      )
    : {};

const builder = await createBuilder();

// Azure AI Foundry settings. The API key is a secret parameter: taken from backend/.env when present,
// otherwise the dashboard asks for it on first run and keeps it in local user secrets.
const foundryEndpoint = await builder.addParameter('foundry-endpoint', {
    value: dotenv.AZURE_FOUNDRY_ENDPOINT ?? 'https://ai-weeks.services.ai.azure.com/openai/v1/',
});
const foundryApiKey = await builder.addParameter('foundry-api-key', {
    secret: true,
    ...(dotenv.AZURE_FOUNDRY_API_KEY ? { value: dotenv.AZURE_FOUNDRY_API_KEY } : {}),
});

const backend = await builder
    .addUvicornApp('backend', './backend', 'app.main:app')
    .withUv()
    .withEnvironment('AZURE_FOUNDRY_ENDPOINT', foundryEndpoint)
    .withEnvironment('AZURE_FOUNDRY_API_KEY', foundryApiKey)
    .withEnvironment('CHAT_DEPLOYMENT', 'gpt-5.6-terra')
    .withEnvironment('VISION_DEPLOYMENT', 'gpt-5.6-terra')
    .withEnvironment('EMBEDDING_DEPLOYMENT', 'text-embedding-3-small')
    .withHttpHealthCheck({ path: '/api/health' });

await builder
    .addViteApp('frontend', './triage-explorer')
    .withReference(backend)
    .waitFor(backend)
    // Fixed port so the Cloudflare tunnel (ai-weeks.p7e.dev) always has the same origin to point at.
    .withHttpEndpointCallback(async (endpoint) => {
        await endpoint.port.set(5173);
    })
    .withExternalHttpEndpoints();

await builder.build().run();

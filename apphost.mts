// Aspire TypeScript AppHost — runs the triage backend (FastAPI/uv) and the React frontend (Vite) locally.
// Start with: aspire run
import { existsSync, readFileSync } from 'node:fs';
import { parseEnv } from 'node:util';
import { createBuilder } from './.aspire/modules/aspire.mjs';

// backend/.env (gitignored) is the single place for local settings, shared with standalone `uvicorn` runs.
const dotenv: Record<string, string | undefined> = existsSync('./backend/.env')
    ? parseEnv(readFileSync('./backend/.env', 'utf8'))
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
    .withHttpHealthCheck({ path: '/api/health' });

// Keep secrets on server resources; never inject them into Vite/browser variables.
for (const [name, value] of Object.entries(dotenv)) {
    if (!value || name.startsWith('AZURE_FOUNDRY_') || name.startsWith('JEV_')) continue;
    const setting = /KEY|TOKEN|SECRET/.test(name)
        ? await builder.addParameter(name.toLowerCase().replaceAll('_', '-'), { secret: true, value })
        : value;
    await backend.withEnvironment(name, setting);
}

const intakeBackend = await builder.addPythonApp('intake-backend', './intake', 'server.py')
    .withUv()
    .withHttpEndpoint({ env: 'PORT' })
    .withEnvironment('TRIAGE_BACKEND_URL', backend.getEndpoint('http'))
    .withReference(backend)
    .waitFor(backend)
    .withHttpHealthCheck({ path: '/api/health' });

for (const name of ['JEV_API_KEY', 'JEV_MODEL', 'OPENAI_API_KEY', 'OPENAI_MODEL']) {
    if (!dotenv[name]) continue;
    const setting = name.endsWith('_KEY')
        ? await builder.addParameter(`intake-${name.toLowerCase().replaceAll('_', '-')}`, { secret: true, value: dotenv[name] })
        : dotenv[name];
    await intakeBackend.withEnvironment(name, setting);
}

await builder.addViteApp('intake', './intake')
    .withReference(intakeBackend)
    .withEnvironment('BACKEND_URL', intakeBackend.getEndpoint('http'))
    .waitFor(intakeBackend)
    .withHttpEndpointCallback(async endpoint => { await endpoint.port.set(8080); })
    .withExternalHttpEndpoints();

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

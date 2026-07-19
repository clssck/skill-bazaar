#!/usr/bin/env node

import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourcesPath = resolve(root, "sources.json");
const catalogPath = resolve(root, ".omp-plugin/marketplace.json");
const checkOnly = process.argv.includes("--check");
const token = process.env.GITHUB_TOKEN;
const headers = {
  Accept: "application/vnd.github+json",
  "X-GitHub-Api-Version": "2022-11-28",
  "User-Agent": "clssck-skill-bazaar",
  ...(token ? { Authorization: `Bearer ${token}` } : {}),
};

async function githubJson(path) {
  const response = await fetch(`https://api.github.com${path}`, { headers });
  if (!response.ok) {
    throw new Error(`GitHub ${response.status} for ${path}: ${await response.text()}`);
  }
  return response.json();
}

async function readUpstreamManifest(source, sha) {
  if (!source.manifest) return null;

  const path = `/repos/${source.repo}/contents/${source.manifest}?ref=${sha}`;
  const payload = await githubJson(path);
  if (payload.type !== "file" || payload.encoding !== "base64") {
    throw new Error(`Expected a base64 file response for ${source.repo}/${source.manifest}`);
  }
  return JSON.parse(Buffer.from(payload.content, "base64").toString("utf8"));
}

function parseVersion(version) {
  const match = /^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$/.exec(version ?? "");
  if (!match) throw new Error(`Expected a semantic version, received ${JSON.stringify(version)}`);
  return match.slice(1).map(part => BigInt(part));
}

function compareVersions(left, right) {
  const a = parseVersion(left);
  const b = parseVersion(right);
  for (let index = 0; index < 3; index += 1) {
    if (a[index] > b[index]) return 1;
    if (a[index] < b[index]) return -1;
  }
  return 0;
}

function resolveVersion(baseVersion, committedAt, previousEntry, sha) {
  if (previousEntry?.source?.sha === sha) return previousEntry.version;

  const [major, minor] = parseVersion(baseVersion);
  const epochSeconds = Math.floor(Date.parse(committedAt) / 1000);
  if (!Number.isSafeInteger(epochSeconds) || epochSeconds <= 0) {
    throw new Error(`Invalid upstream commit timestamp: ${committedAt}`);
  }

  let candidate = `${major}.${minor}.${epochSeconds}`;
  if (previousEntry && compareVersions(candidate, previousEntry.version) <= 0) {
    const [previousMajor, previousMinor, previousPatch] = parseVersion(previousEntry.version);
    candidate = `${previousMajor}.${previousMinor}.${previousPatch + 1n}`;
  }
  return candidate;
}

function normalizeAuthor(author) {
  if (typeof author === "string") return { name: author };
  if (!author?.name) return undefined;
  return {
    name: author.name,
    ...(author.email ? { email: author.email } : {}),
  };
}

function normalizeRepository(repository) {
  if (typeof repository === "string") return repository;
  return repository?.url;
}

function compact(object) {
  return Object.fromEntries(Object.entries(object).filter(([, value]) => value !== undefined));
}

const sources = JSON.parse(await readFile(sourcesPath, "utf8"));
let previousCatalog = { plugins: [] };
try {
  previousCatalog = JSON.parse(await readFile(catalogPath, "utf8"));
} catch (error) {
  if (error?.code !== "ENOENT") throw error;
}
const previousEntries = new Map(previousCatalog.plugins.map(entry => [entry.name, entry]));

const plugins = [];
for (const source of sources.plugins) {
  const commit = await githubJson(`/repos/${source.repo}/commits/${source.ref}`);
  const manifest = await readUpstreamManifest(source, commit.sha);
  const baseVersion = manifest?.version ?? source.baseVersion;
  if (!baseVersion) {
    throw new Error(`${source.name} needs either an upstream manifest version or baseVersion`);
  }

  const name = source.name ?? manifest?.name;
  if (!name) throw new Error(`${source.repo} did not resolve a plugin name`);

  const previousEntry = previousEntries.get(name);
  const version = resolveVersion(
    baseVersion,
    commit.commit.committer.date,
    previousEntry,
    commit.sha,
  );
  const author = normalizeAuthor(source.author ?? manifest?.author);
  const repository = source.repository ?? normalizeRepository(manifest?.repository);
  const tags = source.tags ?? manifest?.keywords;

  plugins.push(compact({
    name,
    version,
    source: {
      source: "github",
      repo: source.repo,
      ref: source.ref,
      sha: commit.sha,
    },
    description: source.description ?? manifest?.description,
    author,
    homepage: source.homepage ?? manifest?.homepage,
    repository,
    license: source.license ?? manifest?.license,
    category: source.category,
    tags,
  }));
}

const catalog = {
  name: sources.marketplace.name,
  owner: sources.marketplace.owner,
  metadata: {
    description: sources.marketplace.description,
  },
  plugins,
};
const rendered = `${JSON.stringify(catalog, null, 2)}\n`;
const current = await readFile(catalogPath, "utf8").catch(() => "");

if (current === rendered) {
  console.log("Marketplace catalog is current.");
} else if (checkOnly) {
  console.error("Marketplace catalog is stale. Run: node scripts/sync-catalog.mjs");
  process.exitCode = 1;
} else {
  await writeFile(catalogPath, rendered);
  console.log(`Updated ${catalogPath}`);
}

#!/usr/bin/env node

import { readFile, writeFile } from "node:fs/promises";
import { dirname, posix, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourcesPath = resolve(root, "sources.json");
const catalogPath = resolve(root, ".omp-plugin/marketplace.json");
const token = process.env.GITHUB_TOKEN;
const headers = {
  Accept: "application/vnd.github+json",
  "X-GitHub-Api-Version": "2022-11-28",
  "User-Agent": "clssck-skill-bazaar",
  ...(token ? { Authorization: `Bearer ${token}` } : {}),
};
const repositoryCache = new Map();
const contextCache = new Map();
const blobCache = new Map();

async function githubJson(path, optional = false) {
  const response = await fetch(`https://api.github.com${path}`, { headers });
  if (optional && response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`GitHub ${response.status} for ${path}: ${await response.text()}`);
  }
  return response.json();
}

function parseGitHubRepository(value) {
  const normalized = value.includes("://") ? value : `https://github.com/${value}`;
  const url = new URL(normalized);
  if (url.hostname !== "github.com") {
    throw new Error(`Only GitHub repositories are supported: ${value}`);
  }
  const parts = url.pathname.replace(/^\/+|\/+$/g, "").replace(/\.git$/, "").split("/");
  if (parts.length !== 2 || parts.some(part => !part)) {
    throw new Error(`Expected a GitHub repository URL or owner/repo slug: ${value}`);
  }
  return `${parts[0]}/${parts[1]}`;
}

function slug(value) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

function compact(object) {
  return Object.fromEntries(Object.entries(object).filter(([, value]) => value !== undefined));
}

async function repositoryMetadata(repo) {
  if (!repositoryCache.has(repo)) repositoryCache.set(repo, githubJson(`/repos/${repo}`));
  return repositoryCache.get(repo);
}

async function repositoryContext(repo, revision) {
  const metadata = await repositoryMetadata(repo);
  const ref = revision || metadata.default_branch;
  const cacheKey = `${repo}@${ref}`;
  if (!contextCache.has(cacheKey)) {
    contextCache.set(cacheKey, (async () => {
      const commit = await githubJson(`/repos/${repo}/commits/${encodeURIComponent(ref)}`);
      const tree = await githubJson(`/repos/${repo}/git/trees/${commit.sha}?recursive=1`);
      if (tree.truncated) throw new Error(`GitHub returned a truncated tree for ${repo}@${commit.sha}`);
      const files = tree.tree.filter(entry => entry.type === "blob");
      return {
        repo,
        ref,
        sha: commit.sha,
        committedAt: commit.commit.committer?.date ?? commit.commit.author?.date,
        metadata,
        files,
        fileMap: new Map(files.map(entry => [entry.path, entry])),
      };
    })());
  }
  return contextCache.get(cacheKey);
}

async function readBlob(context, sha) {
  const key = `${context.repo}:${sha}`;
  if (!blobCache.has(key)) {
    blobCache.set(key, (async () => {
      const payload = await githubJson(`/repos/${context.repo}/git/blobs/${sha}`);
      if (payload.encoding !== "base64") {
        throw new Error(`Expected a base64 blob for ${context.repo}:${sha}`);
      }
      return Buffer.from(payload.content, "base64");
    })());
  }
  return blobCache.get(key);
}

async function readJsonAt(context, path) {
  const entry = context.fileMap.get(path);
  if (!entry) return null;
  return JSON.parse((await readBlob(context, entry.sha)).toString("utf8"));
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

function resolveVersion(baseVersion, context, previousEntry) {
  if (previousEntry?.source?.sha === context.sha) return previousEntry.version;

  const [major, minor] = parseVersion(baseVersion);
  const epochSeconds = Math.floor(Date.parse(context.committedAt) / 1000);
  if (!Number.isSafeInteger(epochSeconds) || epochSeconds <= 0) {
    throw new Error(`Invalid commit timestamp for ${context.repo}: ${context.committedAt}`);
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
  return compact({ name: author.name, email: author.email });
}

function normalizeRepository(repository) {
  if (typeof repository === "string") return repository;
  return repository?.url;
}

function licenseName(metadata) {
  const value = metadata.license?.spdx_id;
  return value && value !== "NOASSERTION" ? value : undefined;
}

function catalogSource(context, subdirectory = "") {
  if (!subdirectory || subdirectory === ".") {
    return { source: "github", repo: context.repo, ref: context.ref, sha: context.sha };
  }
  return {
    source: "git-subdir",
    url: `https://github.com/${context.repo}.git`,
    path: subdirectory,
    ref: context.ref,
    sha: context.sha,
  };
}

function sourceIdentity(source) {
  if (source?.source === "github") return `${source.repo}#${source.path ?? ""}`;
  if (source?.source === "git-subdir") return `${parseGitHubRepository(source.url)}#${source.path}`;
  if (source?.source === "url") return `${parseGitHubRepository(source.url)}#`;
  return null;
}

function previousEntryFor(name, context, subdirectory = "") {
  const identity = sourceIdentity(catalogSource(context, subdirectory));
  return previousCatalog.plugins.find(entry => sourceIdentity(entry.source) === identity)
    ?? previousCatalog.plugins.find(entry => entry.name === name);
}

function sourceRepositorySlug(source) {
  if (source?.source === "github") return slug(source.repo);
  if (source?.source === "git-subdir" || source?.source === "url") {
    return slug(parseGitHubRepository(source.url));
  }
  return "external";
}

async function pluginManifest(context, subdirectory = "") {
  const candidates = [
    posix.join(subdirectory, ".omp-plugin/plugin.json"),
    posix.join(subdirectory, ".claude-plugin/plugin.json"),
    posix.join(subdirectory, "package.json"),
  ];
  for (const candidate of candidates) {
    const manifest = await readJsonAt(context, candidate);
    if (manifest) return manifest;
  }
  return null;
}

function pluginMetadata({ entry = {}, manifest = {}, context, category, description }) {
  entry ??= {};
  manifest ??= {};
  return compact({
    description: entry.description ?? manifest.description ?? description ?? context.metadata.description,
    author: normalizeAuthor(entry.author ?? manifest.author ?? { name: context.metadata.owner.login }),
    homepage: entry.homepage ?? manifest.homepage,
    repository: entry.repository ?? normalizeRepository(manifest.repository) ?? context.metadata.html_url,
    license: entry.license ?? manifest.license ?? licenseName(context.metadata),
    category: entry.category ?? category,
    tags: entry.tags ?? entry.keywords ?? manifest.keywords,
  });
}

function findMarketplacePath(context) {
  return [".omp-plugin/marketplace.json", ".claude-plugin/marketplace.json"]
    .find(path => context.fileMap.has(path));
}

async function resolveImportedSource(parentContext, source) {
  if (typeof source === "string") {
    if (!source.startsWith("./")) throw new Error(`Invalid relative plugin source: ${source}`);
    return { context: parentContext, subdirectory: source.slice(2).replace(/\/$/, "") };
  }
  if (!source || typeof source !== "object") throw new Error("Plugin source is missing");

  if (source.source === "github") {
    return {
      context: await repositoryContext(source.repo, source.ref ?? source.sha),
      subdirectory: source.path ?? "",
    };
  }
  if (source.source === "git-subdir") {
    return {
      context: await repositoryContext(parseGitHubRepository(source.url), source.ref ?? source.sha),
      subdirectory: source.path,
    };
  }
  if (source.source === "url") {
    return {
      context: await repositoryContext(parseGitHubRepository(source.url), source.ref ?? source.sha),
      subdirectory: "",
    };
  }
  throw new Error(`Unsupported imported plugin source: ${source.source}`);
}

async function importMarketplace(context, marketplace) {
  const plugins = [];
  for (const entry of marketplace.plugins ?? []) {
    const target = await resolveImportedSource(context, entry.source);
    const manifest = await pluginManifest(target.context, target.subdirectory);
    const name = entry.name ?? manifest?.name;
    if (!name) throw new Error(`Marketplace entry in ${context.repo} has no plugin name`);
    plugins.push({
      name,
      version: resolveVersion(entry.version ?? manifest?.version ?? "1.0.0", target.context, previousEntryFor(name, target.context, target.subdirectory)),
      source: catalogSource(target.context, target.subdirectory),
      ...(entry.skills === undefined ? {} : { skills: entry.skills }),
      ...pluginMetadata({ entry, manifest, context: target.context }),
    });
  }
  return plugins;
}

function declaredSkillPaths(manifest) {
  if (typeof manifest?.skills === "string") return [manifest.skills];
  return Array.isArray(manifest?.skills) ? manifest.skills.filter(value => typeof value === "string") : [];
}

async function directRepositoryPlugin(context) {
  const manifest = await pluginManifest(context);
  const [owner, repoName] = context.repo.split("/");
  const name = slug(manifest?.name ?? `${owner}-${repoName}`);
  return {
    name,
    version: resolveVersion(manifest?.version ?? "1.0.0", context, previousEntryFor(name, context)),
    source: catalogSource(context),
    ...pluginMetadata({ manifest, context }),
  };
}

function parseSkillFrontmatter(content, fallback) {
  const frontmatter = /^---\s*\r?\n([\s\S]*?)\r?\n---/.exec(content)?.[1] ?? "";
  const field = key => {
    const value = new RegExp(`^${key}:\\s*(.*?)\\s*$`, "m").exec(frontmatter)?.[1]?.trim();
    if (!value) return undefined;
    const quote = value[0];
    return (quote === `"` || quote === `'`) && value.at(-1) === quote ? value.slice(1, -1) : value;
  };
  const name = slug(field("name") ?? fallback);
  if (!name) throw new Error(`Could not determine a skill name for ${fallback}`);
  return { name, description: field("description") };
}

async function standaloneRepositoryPlugins(context) {
  const entries = context.files.filter(entry => /(^|\/)SKILL\.md$/.test(entry.path));
  if (entries.length === 0) throw new Error(`${context.repo} contains no discoverable SKILL.md files`);

  const plugins = [];
  for (const entry of entries) {
    const directory = posix.dirname(entry.path) === "." ? "" : posix.dirname(entry.path);
    const fallback = directory ? posix.basename(directory) : context.repo.split("/")[1];
    const frontmatter = parseSkillFrontmatter((await readBlob(context, entry.sha)).toString("utf8"), fallback);
    plugins.push({
      name: frontmatter.name,
      version: resolveVersion("1.0.0", context, previousEntryFor(frontmatter.name, context, directory)),
      source: catalogSource(context, directory),
      skills: ".",
      ...pluginMetadata({ context, category: "standalone-skill", description: frontmatter.description }),
      tags: ["github-skills", "standalone-skill"],
    });
  }
  return plugins;
}

const sources = JSON.parse(await readFile(sourcesPath, "utf8"));
let previousCatalog = { plugins: [] };
try {
  previousCatalog = JSON.parse(await readFile(catalogPath, "utf8"));
} catch (error) {
  if (error?.code !== "ENOENT") throw error;
}
const plugins = [];

for (const repository of sources.repositories) {
  const repo = parseGitHubRepository(repository);
  const context = await repositoryContext(repo);
  const marketplacePath = findMarketplacePath(context);
  if (marketplacePath) {
    plugins.push(...await importMarketplace(context, await readJsonAt(context, marketplacePath)));
    continue;
  }

  const manifest = await pluginManifest(context);
  const hasConventionalSkills = context.files.some(entry => /^skills\/[^/]+\/SKILL\.md$/.test(entry.path));
  if (hasConventionalSkills || declaredSkillPaths(manifest).length > 0) {
    plugins.push(await directRepositoryPlugin(context));
  } else {
    plugins.push(...await standaloneRepositoryPlugins(context));
  }
}

const nameCounts = new Map();
for (const plugin of plugins) nameCounts.set(plugin.name, (nameCounts.get(plugin.name) ?? 0) + 1);
const usedNames = new Set(plugins.filter(plugin => nameCounts.get(plugin.name) === 1).map(plugin => plugin.name));
for (const plugin of plugins.filter(plugin => nameCounts.get(plugin.name) > 1)) {
  const base = slug(`${sourceRepositorySlug(plugin.source)}-${plugin.name}`);
  let candidate = base;
  let suffix = 2;
  while (usedNames.has(candidate)) candidate = `${base}-${suffix++}`;
  plugin.name = candidate;
  usedNames.add(candidate);
}

const catalog = {
  name: sources.marketplace.name,
  owner: sources.marketplace.owner,
  metadata: { description: sources.marketplace.description },
  plugins,
};
const rendered = `${JSON.stringify(catalog, null, 2)}\n`;
const current = await readFile(catalogPath, "utf8").catch(() => "");
if (current === rendered) {
  console.log("Marketplace catalog is current.");
} else {
  await writeFile(catalogPath, rendered);
  console.log(`Updated ${catalogPath}`);
}

const dotenv = require("dotenv");

dotenv.config();

function parseList(value) {
  if (!value) {
    return [];
  }

  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseRoleMap(value) {
  if (!value) {
    return {};
  }

  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function toPositiveInt(value, fallback) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function normalizeApiBaseUrl(value) {
  if (!value) {
    return value;
  }

  let normalized = String(value).trim();
  normalized = normalized.replace(/\/+$/, "");

  // Keep base URL clean so endpoint paths can consistently add /api.
  if (/\/api$/i.test(normalized)) {
    normalized = normalized.replace(/\/api$/i, "");
  }

  return normalized;
}

const config = {
  discordToken: process.env.DISCORD_TOKEN,
  discordClientId: process.env.DISCORD_CLIENT_ID,
  discordGuildId: process.env.DISCORD_GUILD_ID,
  commandPrefix: process.env.COMMAND_PREFIX || "!",
  adminRoleName: process.env.ADMIN_ROLE_NAME || "Admin",
  logChannelIds: parseList(process.env.LOG_CHANNEL_IDS),
  apiBaseUrl: normalizeApiBaseUrl(process.env.SILVERSHADE_API || process.env.API_BASE_URL),
  apiKey: process.env.SILVERSHADE_API_KEY || process.env.API_KEY,
  adminToken: process.env.SILVERSHADE_ADMIN_TOKEN,
  pollIntervalMs: toPositiveInt(process.env.POLL_INTERVAL_MS, 5000),
  backendRoleMap: parseRoleMap(process.env.BACKEND_ROLE_MAP)
};

function validateConfig() {
  const required = [
    ["DISCORD_TOKEN", config.discordToken],
    ["DISCORD_GUILD_ID", config.discordGuildId],
    ["SILVERSHADE_API", config.apiBaseUrl],
    ["SILVERSHADE_API_KEY", config.apiKey]
  ];

  const missing = required.filter(([, value]) => !value).map(([key]) => key);

  if (missing.length > 0) {
    throw new Error(`Missing required environment variables: ${missing.join(", ")}`);
  }
}

module.exports = {
  config,
  validateConfig
};

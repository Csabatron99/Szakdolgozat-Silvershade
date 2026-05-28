const dotenv = require('dotenv');

dotenv.config();

const apiBaseUrl = process.env.SILVERSHADE_API || process.env.BACKEND_API_BASE_URL;
const serviceApiKey = process.env.SILVERSHADE_API_KEY || process.env.BACKEND_API_KEY;

const requiredConfig = {
  SILVERSHADE_API: apiBaseUrl,
  SILVERSHADE_API_KEY: serviceApiKey
};

for (const [key, value] of Object.entries(requiredConfig)) {
  if (!value) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
}

const toNumber = (value, fallback) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

module.exports = {
  port: toNumber(process.env.PORT, 3000),
  backendApiBaseUrl: apiBaseUrl,
  backendApiKey: serviceApiKey,
  adminToken: process.env.SILVERSHADE_ADMIN_TOKEN,
  pollIntervalMs: toNumber(process.env.POLL_INTERVAL_MS, 5000),
  maxRetries: toNumber(process.env.MAX_RETRIES, 3),
  retryBaseDelayMs: toNumber(process.env.RETRY_BASE_DELAY_MS, 500),
  logFilePath: process.env.LOG_FILE_PATH || 'logs/server.log'
};

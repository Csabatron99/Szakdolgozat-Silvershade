const axios = require('axios');
const env = require('../config/env');
const { withRetry } = require('../utils/retry');

function normalizeBaseUrl(url) {
  const trimmed = String(url || '').trim();
  const withoutTrailingSlash = trimmed.replace(/\/+$/, '');
  return withoutTrailingSlash.replace(/\/api$/i, '');
}

const normalizedBaseUrl = normalizeBaseUrl(env.backendApiBaseUrl);

const client = axios.create({
  baseURL: normalizedBaseUrl,
  timeout: 5000,
  headers: {
    Authorization: `Bearer ${env.backendApiKey}`,
    'Content-Type': 'application/json'
  }
});

function getErrorMessage(error) {
  const status = error?.response?.status;
  const data = error?.response?.data;
  if (status) {
    return `HTTP ${status}: ${JSON.stringify(data)}`;
  }

  return error.message || 'Unknown API error';
}

async function getSyncUpdates() {
  return withRetry(
    async () => {
      try {
        const response = await client.get('/api/v1/sync/updates');
        return response.data || {};
      } catch (error) {
        throw new Error(getErrorMessage(error));
      }
    },
    {
      retries: env.maxRetries,
      baseDelayMs: env.retryBaseDelayMs,
      operationName: 'getSyncUpdates'
    }
  );
}

async function getPendingTransactions() {
  const payload = await getSyncUpdates();
  return payload.transactions || payload.pendingTransactions || [];
}

async function confirmTransaction(transactionId) {
  return withRetry(
    async () => {
      try {
        const response = await client.patch(`/api/v1/transactions/${encodeURIComponent(transactionId)}/status`, {
          status: 'completed'
        });
        return response.data;
      } catch (error) {
        throw new Error(getErrorMessage(error));
      }
    },
    {
      retries: env.maxRetries,
      baseDelayMs: env.retryBaseDelayMs,
      operationName: 'confirmTransaction'
    }
  );
}

async function getAdminActions() {
  const payload = await getSyncUpdates();
  return payload.adminActions || payload.pendingAdminActions || [];
}

async function confirmAdminAction(adminActionId) {
  return withRetry(
    async () => {
      try {
        const response = await client.patch(`/api/v1/admin-actions/${encodeURIComponent(adminActionId)}/status`, {
          status: 'completed'
        });
        return response.data;
      } catch (error) {
        throw new Error(getErrorMessage(error));
      }
    },
    {
      retries: env.maxRetries,
      baseDelayMs: env.retryBaseDelayMs,
      operationName: 'confirmAdminAction'
    }
  );
}

async function simulateFivemRewards() {
  if (!env.adminToken) {
    throw new Error('Missing SILVERSHADE_ADMIN_TOKEN for admin simulation endpoint');
  }

  try {
    const response = await axios.post(
      `${normalizedBaseUrl}/api/v1/admin/simulate-fivem-rewards`,
      {},
      {
        timeout: 10000,
        headers: {
          Authorization: `Bearer ${env.adminToken}`,
          'Content-Type': 'application/json'
        }
      }
    );

    return response.data;
  } catch (error) {
    throw new Error(getErrorMessage(error));
  }
}

async function simulateFivemActions() {
  if (!env.adminToken) {
    throw new Error('Missing SILVERSHADE_ADMIN_TOKEN for admin simulation endpoint');
  }

  try {
    const response = await axios.post(
      `${normalizedBaseUrl}/api/v1/admin/simulate-fivem-actions`,
      {},
      {
        timeout: 10000,
        headers: {
          Authorization: `Bearer ${env.adminToken}`,
          'Content-Type': 'application/json'
        }
      }
    );

    return response.data;
  } catch (error) {
    throw new Error(getErrorMessage(error));
  }
}

async function pushPlayers(players) {
  return withRetry(
    async () => {
      try {
        const response = await client.post('/api/v1/service/fivem/players', { players });
        return response.data;
      } catch (error) {
        throw new Error(getErrorMessage(error));
      }
    },
    {
      retries: env.maxRetries,
      baseDelayMs: env.retryBaseDelayMs,
      operationName: 'pushPlayers'
    }
  );
}

module.exports = {
  getSyncUpdates,
  getPendingTransactions,
  confirmTransaction,
  getAdminActions,
  confirmAdminAction,
  simulateFivemRewards,
  simulateFivemActions,
  pushPlayers,
  normalizedBaseUrl
};

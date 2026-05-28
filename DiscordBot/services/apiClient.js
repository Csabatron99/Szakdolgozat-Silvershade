const axios = require("axios");

class ApiClient {
  constructor({ baseUrl, apiKey, adminToken, logger }) {
    this.logger = logger;
    this.adminToken = adminToken;
    this.client = axios.create({
      baseURL: baseUrl,
      timeout: 10000,
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json"
      }
    });
  }

  sanitizeError(error) {
    if (error.response) {
      return {
        status: error.response.status,
        message: error.response.data?.message || "API request failed"
      };
    }

    return { message: error.message || "Unknown API error" };
  }

  async request(method, url, data, params) {
    try {
      const response = await this.client.request({ method, url, data, params });
      return response.data;
    } catch (error) {
      const safeError = this.sanitizeError(error);
      this.logger.error(`API ${method.toUpperCase()} ${url} failed`, safeError);
      throw new Error(safeError.message);
    }
  }

  async getUser(userId) {
    return this.request("get", `/api/users/${encodeURIComponent(userId)}`);
  }

  async banUser(payload) {
    return this.request("post", "/api/admin/ban", payload);
  }

  async kickUser(payload) {
    return this.request("post", "/api/admin/kick", payload);
  }

  async createTransaction(payload) {
    return this.request("post", "/api/transactions", payload);
  }

  async assignRole(payload) {
    return this.request("post", "/api/roles/assign", payload);
  }

  async getRecentTransactions(limit = 10) {
    return this.request("get", "/api/transactions/recent", undefined, { limit });
  }

  // Polling endpoint keeps Discord, website, and game server in sync.
  async pollUpdates(cursor) {
    return this.request("get", "/api/v1/sync/updates", undefined, {
      cursor
    });
  }

  async updateDiscordRole(payload) {
    return this.request("post", "/api/discord/roles/sync", payload);
  }

  async simulateDiscordPickup() {
    try {
      const response = await this.client.post(
        "/api/v1/admin/simulate-discord-pickup",
        {},
        {
          headers: {
            Authorization: `Bearer ${this.adminToken}`
          }
        }
      );

      return response.data;
    } catch (error) {
      const safeError = this.sanitizeError(error);
      this.logger.error("API POST /api/v1/admin/simulate-discord-pickup failed", safeError);
      throw new Error(safeError.message);
    }
  }
}

module.exports = ApiClient;

const logger = require('./logger');

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function withRetry(task, options = {}) {
  const {
    retries = 3,
    baseDelayMs = 500,
    operationName = 'operation'
  } = options;

  let lastError;

  for (let attempt = 1; attempt <= retries + 1; attempt += 1) {
    try {
      return await task(attempt);
    } catch (error) {
      lastError = error;
      const isLastAttempt = attempt > retries;

      if (isLastAttempt) {
        break;
      }

      const jitter = Math.floor(Math.random() * 100);
      const delay = baseDelayMs * attempt + jitter;
      logger.warn(`${operationName} failed. Retrying...`, {
        attempt,
        delay,
        error: error.message
      });
      await sleep(delay);
    }
  }

  throw lastError;
}

module.exports = {
  withRetry
};

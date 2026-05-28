const express = require('express');
const env = require('./config/env');
const logger = require('./utils/logger');
const apiClient = require('./services/apiClient');
const playerManager = require('./services/playerManager');

const app = express();
app.use(express.json());

function parseCliFlags(args) {
  return {
    simulateRewards: args.includes('--simulate-rewards'),
    simulateActions: args.includes('--simulate-actions'),
    simulateAll: args.includes('--simulate-all')
  };
}

function requireApiKey(req, res, next) {
  const authHeader = req.headers.authorization;
  const expected = `Bearer ${env.backendApiKey}`;

  if (!authHeader || authHeader !== expected) {
    return res.status(401).json({
      error: 'Unauthorized: invalid or missing API key'
    });
  }

  return next();
}

app.get('/health', (req, res) => {
  res.status(200).json({
    status: 'ok',
    service: 'fivem-dummy-server',
    timestamp: new Date().toISOString()
  });
});

app.get('/players', requireApiKey, (req, res) => {
  res.status(200).json({
    players: playerManager.listPlayers()
  });
});

let isPolling = false;

function parseUpdates(payload) {
  const source = payload?.data || payload?.updates || payload || {};
  const transactions = Array.isArray(source.transactions)
    ? source.transactions
    : Array.isArray(source.pendingTransactions)
      ? source.pendingTransactions
      : [];
  const adminActions = Array.isArray(source.adminActions)
    ? source.adminActions
    : Array.isArray(source.pendingAdminActions)
      ? source.pendingAdminActions
      : [];

  return { transactions, adminActions };
}

function getBackendMessage(responsePayload) {
  if (responsePayload?.data && typeof responsePayload.data.message === 'string') {
    return responsePayload.data.message;
  }

  if (responsePayload && typeof responsePayload.message === 'string') {
    return responsePayload.message;
  }

  return null;
}

async function processTransactions(transactions) {
  try {
    let confirmedCount = 0;
    let failedCount = 0;
    let skippedInvalidCount = 0;

    if (transactions.length === 0) {
      logger.info('No pending transactions found');
      return;
    }

    logger.info('Pending transactions received', { count: transactions.length });

    for (const transaction of transactions) {
      const transactionId = transaction.id;
      try {
        const validation = playerManager.validateTransaction(transaction);
        if (!validation.valid) {
          skippedInvalidCount += 1;
          logger.warn('Skipping invalid transaction payload', {
            transaction,
            reason: validation.reason
          });
          continue;
        }

        logger.info('Processing transaction', { transaction });

        // In a real FiveM resource this becomes ESX/QBCore inventory/economy calls.
        playerManager.applyTransaction(transaction);
        const confirmResponse = await apiClient.confirmTransaction(transactionId);
        const message = getBackendMessage(confirmResponse);

        confirmedCount += 1;

        logger.info('Transaction confirmed', {
          transactionId,
          message
        });
      } catch (error) {
        failedCount += 1;
        logger.error('Failed to process transaction', {
          transactionId,
          error: error.message
        });
      }
    }

    logger.info('Transaction confirmation summary', {
      received: transactions.length,
      confirmed: confirmedCount,
      skippedInvalid: skippedInvalidCount,
      failed: failedCount
    });
  } catch (error) {
    logger.error('Transaction polling failed', { error: error.message });
  }
}

async function processAdminActions(actions) {
  try {
    let confirmedCount = 0;
    let failedCount = 0;
    let skippedInvalidCount = 0;

    if (actions.length === 0) {
      logger.info('No pending admin actions found');
      return;
    }

    logger.info('Pending admin actions received', { count: actions.length });

    for (const action of actions) {
      const adminActionId = action.id;
      try {
        const validation = playerManager.validateAdminAction(action);
        if (!validation.valid) {
          skippedInvalidCount += 1;
          logger.warn('Skipping invalid admin action payload', {
            action,
            reason: validation.reason
          });
          continue;
        }

        logger.info('Processing admin action', { action });
        playerManager.applyAdminAction(action);
        const confirmResponse = await apiClient.confirmAdminAction(adminActionId);
        const message = getBackendMessage(confirmResponse);

        confirmedCount += 1;

        logger.info('Admin action confirmed', {
          adminActionId,
          message
        });
      } catch (error) {
        failedCount += 1;
        logger.error('Failed to process admin action', {
          adminActionId,
          error: error.message
        });
      }
    }

    logger.info('Admin action confirmation summary', {
      received: actions.length,
      confirmed: confirmedCount,
      skippedInvalid: skippedInvalidCount,
      failed: failedCount
    });
  } catch (error) {
    logger.error('Admin action polling failed', { error: error.message });
  }
}

async function processCycle() {
  // Prevent overlapping cycles to avoid duplicate backend processing.
  if (isPolling) {
    logger.warn('Previous polling run still active, skipping this cycle');
    return;
  }

  isPolling = true;

  try {
    const updatesPayload = await apiClient.getSyncUpdates();
    const { transactions, adminActions } = parseUpdates(updatesPayload);

    logger.info('Sync updates received', {
      transactions: transactions.length,
      adminActions: adminActions.length
    });

    await processTransactions(transactions);
    await processAdminActions(adminActions);

    // Push current player list to the backend admin dashboard snapshot.
    try {
      const players = playerManager.listPlayers();
      await apiClient.pushPlayers(players);
      logger.debug('Player state pushed', { count: players.length });
    } catch (pushError) {
      logger.warn('Failed to push player state', { error: pushError.message });
    }
  } catch (error) {
    logger.error('Sync update polling failed', { error: error.message });
  } finally {
    isPolling = false;
  }
}

async function runSimulationFromCli(flags) {
  const wantsRewards = flags.simulateAll || flags.simulateRewards;
  const wantsActions = flags.simulateAll || flags.simulateActions;

  if (!wantsRewards && !wantsActions) {
    return false;
  }

  if (!env.adminToken) {
    logger.error('Simulation flag requires SILVERSHADE_ADMIN_TOKEN in .env');
    process.exitCode = 1;
    return true;
  }

  logger.info('Simulation mode enabled', {
    baseUrl: apiClient.normalizedBaseUrl,
    simulateRewards: wantsRewards,
    simulateActions: wantsActions
  });

  try {
    if (wantsRewards) {
      const rewardsResponse = await apiClient.simulateFivemRewards();
      logger.info('simulate-fivem-rewards success', {
        message: getBackendMessage(rewardsResponse),
        response: rewardsResponse
      });
    }

    if (wantsActions) {
      const actionsResponse = await apiClient.simulateFivemActions();
      logger.info('simulate-fivem-actions success', {
        message: getBackendMessage(actionsResponse),
        response: actionsResponse
      });
    }
  } catch (error) {
    logger.error('Simulation request failed', { error: error.message });
    process.exitCode = 1;
  }

  return true;
}

function startPolling() {
  logger.info('Starting backend polling', { intervalMs: env.pollIntervalMs });

  // Immediate first run + fixed interval for transactions and admin actions.
  processCycle();
  setInterval(processCycle, env.pollIntervalMs);
}

async function bootstrap() {
  const flags = parseCliFlags(process.argv.slice(2));
  const simulationExecuted = await runSimulationFromCli(flags);

  if (simulationExecuted) {
    return;
  }

  app.listen(env.port, () => {
    logger.info('Dummy FiveM server is running', {
      port: env.port,
      baseUrl: apiClient.normalizedBaseUrl
    });
    startPolling();
  });
}

bootstrap();

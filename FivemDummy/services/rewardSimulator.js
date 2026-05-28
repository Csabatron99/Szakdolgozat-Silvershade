const logger = require('../utils/logger');

async function applyReward(transaction) {
  const { id, playerId, rewards } = transaction;

  // In production FiveM integration, this is where server-side events would be triggered:
  // TriggerClientEvent / exports to inventory + economy resources.
  logger.info('Applying rewards to player (simulation)', {
    transactionId: id,
    playerId,
    rewards
  });

  const money = rewards?.money || 0;
  const items = rewards?.items || [];

  if (money > 0) {
    logger.info('Simulated money reward applied', { playerId, money });
  }

  if (items.length > 0) {
    logger.info('Simulated item rewards applied', { playerId, items });
  }

  return {
    applied: true,
    transactionId: id
  };
}

module.exports = {
  applyReward
};

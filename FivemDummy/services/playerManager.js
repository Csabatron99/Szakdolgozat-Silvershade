const logger = require('../utils/logger');

const players = {
  p1: {
    id: 'p1',
    name: 'Alex',
    money: 1200,
    roles: ['player'],
    banned: false,
    lastKickReason: null,
    inventory: []
  },
  p2: {
    id: 'p2',
    name: 'Jordan',
    money: 550,
    roles: ['player', 'vip'],
    banned: false,
    lastKickReason: null,
    inventory: ['medkit']
  },
  p3: {
    id: 'p3',
    name: 'Morgan',
    money: 80,
    roles: ['player'],
    banned: false,
    lastKickReason: null,
    inventory: []
  }
};

function getPlayer(playerId) {
  return players[playerId] || null;
}

function listPlayers() {
  return Object.values(players);
}

function validateTransaction(transaction) {
  if (!transaction || typeof transaction !== 'object') {
    return { valid: false, reason: 'Transaction payload must be an object' };
  }

  if (!transaction.id || !transaction.playerId) {
    return { valid: false, reason: 'Transaction requires id and playerId' };
  }

  if (!transaction.rewards || typeof transaction.rewards !== 'object') {
    return { valid: false, reason: 'Transaction requires rewards object' };
  }

  const money = transaction.rewards.money;
  const items = transaction.rewards.items;

  if (money !== undefined && !Number.isFinite(Number(money))) {
    return { valid: false, reason: 'rewards.money must be numeric' };
  }

  if (items !== undefined && !Array.isArray(items)) {
    return { valid: false, reason: 'rewards.items must be an array' };
  }

  return { valid: true };
}

function applyTransaction(transaction) {
  const player = getPlayer(transaction.playerId);
  if (!player) {
    throw new Error(`Player not found: ${transaction.playerId}`);
  }

  if (player.banned) {
    throw new Error(`Cannot apply rewards to banned player: ${player.id}`);
  }

  const rewards = transaction.rewards || {};
  const money = Number(rewards.money || 0);
  const items = Array.isArray(rewards.items) ? rewards.items : [];

  // This maps to real FiveM server code where framework exports/events
  // would adjust wallet/bank state and inventory on the live player entity.
  if (money > 0) {
    player.money += money;
  }

  if (items.length > 0) {
    player.inventory.push(...items);
  }

  logger.info('Transaction rewards applied (simulation)', {
    transactionId: transaction.id,
    playerId: player.id,
    moneyApplied: money,
    itemsApplied: items,
    newMoneyBalance: player.money
  });

  return {
    success: true,
    playerId: player.id,
    moneyApplied: money,
    itemsApplied: items
  };
}

function validateAdminAction(action) {
  if (!action || typeof action !== 'object') {
    return { valid: false, reason: 'Admin action payload must be an object' };
  }

  if (!action.id || !action.playerId || !action.actionType) {
    return { valid: false, reason: 'Admin action requires id, playerId and actionType' };
  }

  const supportedTypes = ['ban', 'kick', 'give_role', 'remove_role'];
  if (!supportedTypes.includes(action.actionType)) {
    return { valid: false, reason: `Unsupported actionType: ${action.actionType}` };
  }

  if ((action.actionType === 'give_role' || action.actionType === 'remove_role') && !action.role) {
    return { valid: false, reason: 'Role is required for give_role/remove_role' };
  }

  return { valid: true };
}

function applyAdminAction(action) {
  const player = getPlayer(action.playerId);
  if (!player) {
    throw new Error(`Player not found: ${action.playerId}`);
  }

  // In real FiveM this would be implemented via server events/ACE permissions
  // and framework specific APIs for kicks, bans and role/group changes.
  switch (action.actionType) {
    case 'ban': {
      player.banned = true;
      break;
    }
    case 'kick': {
      player.lastKickReason = action.reason || 'No reason provided';
      break;
    }
    case 'give_role': {
      if (!player.roles.includes(action.role)) {
        player.roles.push(action.role);
      }
      break;
    }
    case 'remove_role': {
      player.roles = player.roles.filter((role) => role !== action.role);
      break;
    }
    default:
      throw new Error(`Unsupported action type: ${action.actionType}`);
  }

  logger.info('Admin action executed (simulation)', {
    adminActionId: action.id,
    playerId: player.id,
    actionType: action.actionType,
    role: action.role || null,
    reason: action.reason || null,
    banned: player.banned,
    roles: player.roles
  });

  return {
    success: true,
    actionType: action.actionType,
    playerId: player.id
  };
}

module.exports = {
  listPlayers,
  validateTransaction,
  applyTransaction,
  validateAdminAction,
  applyAdminAction
};

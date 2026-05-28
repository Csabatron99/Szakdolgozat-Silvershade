class DiscordManager {
  constructor({ client, config, logger }) {
    this.client = client;
    this.config = config;
    this.logger = logger;
  }

  async sendLog(message) {
    for (const channelId of this.config.logChannelIds) {
      try {
        const channel = await this.client.channels.fetch(channelId);
        if (channel && channel.isTextBased()) {
          await channel.send(message);
        }
      } catch (error) {
        this.logger.warn(`Failed sending log to channel ${channelId}`, {
          message: error.message
        });
      }
    }
  }

  async fetchGuildMember(userId) {
    const guild = await this.client.guilds.fetch(this.config.discordGuildId);
    return guild.members.fetch(userId);
  }

  async assignRole(userId, roleName) {
    const member = await this.fetchGuildMember(userId);
    const role = member.guild.roles.cache.find((item) => item.name === roleName);

    if (!role) {
      throw new Error(`Discord role \"${roleName}\" not found`);
    }

    await member.roles.add(role.id);
  }

  async removeRole(userId, roleName) {
    const member = await this.fetchGuildMember(userId);
    const role = member.guild.roles.cache.find((item) => item.name === roleName);

    if (!role) {
      throw new Error(`Discord role \"${roleName}\" not found`);
    }

    await member.roles.remove(role.id);
  }

  async syncBackendRoles(userId, backendRoles) {
    const member = await this.fetchGuildMember(userId);
    const mappedRoleIds = backendRoles
      .map((backendRole) => this.config.backendRoleMap[backendRole])
      .filter(Boolean);

    const currentMappedRoles = member.roles.cache.filter((role) =>
      Object.values(this.config.backendRoleMap).includes(role.id)
    );

    for (const role of currentMappedRoles.values()) {
      if (!mappedRoleIds.includes(role.id)) {
        await member.roles.remove(role.id);
      }
    }

    for (const roleId of mappedRoleIds) {
      if (!member.roles.cache.has(roleId)) {
        await member.roles.add(roleId);
      }
    }
  }

  async handleActionLog(action) {
    if (action.type === "ban") {
      await this.sendLog(`User ${action.userId} was banned`);
      return;
    }

    if (action.type === "kick") {
      await this.sendLog(`User ${action.userId} was kicked`);
      return;
    }

    if (action.type === "give_money") {
      await this.sendLog(`User ${action.userId} received ${action.amount} money`);
      return;
    }

    await this.sendLog(`Admin action: ${action.type}`);
  }

  // This processes updates emitted by the website/game backend and applies them to Discord.
  async processSyncPayload(payload) {
    const transactions = payload?.pendingTransactions || payload?.transactions || [];
    const adminActions = payload?.pendingAdminActions || payload?.adminActions || [];
    const roleUpdates = payload?.roleUpdates || [];

    for (const transaction of transactions) {
      await this.sendLog(
        `Transaction ${transaction.id}: ${transaction.userId} ${transaction.type} ${transaction.amount}`
      );
    }

    for (const action of adminActions) {
      await this.handleActionLog(action);
    }

    for (const roleUpdate of roleUpdates) {
      await this.syncBackendRoles(roleUpdate.userId, roleUpdate.roles || []);
      await this.sendLog(`Roles synchronized for user ${roleUpdate.userId}`);
    }
  }
}

module.exports = DiscordManager;

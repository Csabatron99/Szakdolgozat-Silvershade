module.exports = {
  name: "kick",
  adminOnly: true,
  description: "Kick a user via backend API",
  async execute({ message, args, apiClient, discordManager }) {
    const targetUserId = args[0];
    const reason = args.slice(1).join(" ") || "No reason provided";

    if (!targetUserId || !/^\d{2,32}$/.test(targetUserId)) {
      await message.reply("Usage: !kick <userId> [reason]");
      return;
    }

    try {
      await apiClient.kickUser({
        userId: targetUserId,
        reason,
        moderatorId: message.author.id
      });

      await discordManager.sendLog(`User ${targetUserId} was kicked`);
      await message.reply(`Kick request sent for user ${targetUserId}.`);
    } catch (error) {
      await message.reply(`Kick failed: ${error.message}`);
    }
  }
};

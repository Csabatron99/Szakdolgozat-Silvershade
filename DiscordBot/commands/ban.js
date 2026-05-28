module.exports = {
  name: "ban",
  adminOnly: true,
  description: "Ban a user via backend API",
  async execute({ message, args, apiClient, discordManager }) {
    const targetUserId = args[0];
    const reason = args.slice(1).join(" ") || "No reason provided";

    if (!targetUserId || !/^\d{2,32}$/.test(targetUserId)) {
      await message.reply("Usage: !ban <userId> [reason]");
      return;
    }

    try {
      await apiClient.banUser({
        userId: targetUserId,
        reason,
        moderatorId: message.author.id
      });

      await discordManager.sendLog(`User ${targetUserId} was banned`);
      await message.reply(`Ban request sent for user ${targetUserId}.`);
    } catch (error) {
      await message.reply(`Ban failed: ${error.message}`);
    }
  }
};

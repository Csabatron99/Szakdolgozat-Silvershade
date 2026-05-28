module.exports = {
  name: "give-money",
  adminOnly: true,
  description: "Create a money transaction via backend API",
  async execute({ message, args, apiClient, discordManager }) {
    const targetUserId = args[0];
    const amountRaw = args[1];
    const note = args.slice(2).join(" ") || "Discord admin transaction";

    if (!targetUserId || !/^\d{2,32}$/.test(targetUserId)) {
      await message.reply("Usage: !give-money <userId> <amount> [note]");
      return;
    }

    const amount = Number.parseInt(amountRaw, 10);
    if (!Number.isFinite(amount) || amount <= 0) {
      await message.reply("Amount must be a positive integer.");
      return;
    }

    try {
      await apiClient.createTransaction({
        userId: targetUserId,
        amount,
        type: "credit",
        source: "discord-admin",
        note,
        actorId: message.author.id
      });

      await discordManager.sendLog(`User ${targetUserId} received ${amount} money`);
      await message.reply(`Transaction created: ${targetUserId} +${amount}`);
    } catch (error) {
      await message.reply(`Transaction failed: ${error.message}`);
    }
  }
};

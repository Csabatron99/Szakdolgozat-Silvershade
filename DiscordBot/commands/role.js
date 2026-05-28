module.exports = {
  name: "role",
  adminOnly: true,
  description: "Assign backend role and sync Discord role",
  async execute({ message, args, apiClient, discordManager }) {
    const targetUserId = args[0];
    const roleName = args[1];
    const action = (args[2] || "add").toLowerCase();

    if (!targetUserId || !/^\d{2,32}$/.test(targetUserId) || !roleName) {
      await message.reply("Usage: !role <userId> <roleName> [add|remove]");
      return;
    }

    if (!["add", "remove"].includes(action)) {
      await message.reply("Role action must be add or remove.");
      return;
    }

    try {
      await apiClient.assignRole({
        userId: targetUserId,
        role: roleName,
        action,
        actorId: message.author.id
      });

      if (action === "add") {
        await discordManager.assignRole(targetUserId, roleName);
      } else {
        await discordManager.removeRole(targetUserId, roleName);
      }

      await message.reply(`Role ${roleName} ${action} request completed for ${targetUserId}.`);
    } catch (error) {
      await message.reply(`Role update failed: ${error.message}`);
    }
  }
};

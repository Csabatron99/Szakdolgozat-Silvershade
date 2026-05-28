module.exports = {
  name: "user",
  adminOnly: false,
  description: "Fetch user data from backend API",
  async execute({ message, args, apiClient }) {
    const targetUserId = args[0] || message.author.id;

    if (!/^\d{2,32}$/.test(targetUserId)) {
      await message.reply("Invalid user ID. Use numeric IDs only.");
      return;
    }

    try {
      const user = await apiClient.getUser(targetUserId);
      await message.reply(
        `User ${user.id} | name: ${user.name || "n/a"} | balance: ${user.balance ?? 0}`
      );
    } catch (error) {
      await message.reply(`Failed to fetch user data: ${error.message}`);
    }
  }
};

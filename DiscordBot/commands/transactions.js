module.exports = {
  name: "transactions",
  adminOnly: true,
  description: "List recent transactions from backend API",
  async execute({ message, args, apiClient }) {
    const limitRaw = args[0];
    const limit = limitRaw ? Number.parseInt(limitRaw, 10) : 5;

    if (!Number.isFinite(limit) || limit <= 0 || limit > 20) {
      await message.reply("Usage: !transactions [1-20]");
      return;
    }

    try {
      const transactions = await apiClient.getRecentTransactions(limit);
      if (!Array.isArray(transactions) || transactions.length === 0) {
        await message.reply("No transactions found.");
        return;
      }

      const lines = transactions.map(
        (tx) => `${tx.id}: ${tx.userId} ${tx.type} ${tx.amount} (${tx.createdAt || "n/a"})`
      );

      await message.reply(`Recent transactions:\n${lines.join("\n")}`);
    } catch (error) {
      await message.reply(`Failed to load transactions: ${error.message}`);
    }
  }
};

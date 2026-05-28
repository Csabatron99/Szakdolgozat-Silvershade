module.exports = {
  name: "ping",
  adminOnly: false,
  description: "Test bot availability",
  async execute({ message }) {
    await message.reply("Pong!");
  }
};

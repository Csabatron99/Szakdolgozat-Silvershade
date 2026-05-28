const fs = require("fs");
const path = require("path");
const {
  Client,
  GatewayIntentBits,
  Partials,
  PermissionsBitField
} = require("discord.js");
const { config, validateConfig } = require("./config");
const ApiClient = require("./services/apiClient");
const DiscordManager = require("./services/discordManager");
const logger = require("./services/logger");

validateConfig();
const shouldSimulateDiscordPickup = process.argv.includes("--simulate-discord-pickup");

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.MessageContent
  ],
  partials: [Partials.Channel]
});

const apiClient = new ApiClient({
  baseUrl: config.apiBaseUrl,
  apiKey: config.apiKey,
  adminToken: config.adminToken,
  logger
});

const discordManager = new DiscordManager({ client, config, logger });

function loadCommands() {
  const commandsPath = path.join(__dirname, "commands");
  const files = fs.readdirSync(commandsPath).filter((file) => file.endsWith(".js"));
  const commands = new Map();

  for (const file of files) {
    const commandModule = require(path.join(commandsPath, file));
    commands.set(commandModule.name, commandModule);
  }

  return commands;
}

const commands = loadCommands();

function hasAdminRole(member) {
  if (!member) {
    return false;
  }

  const byRoleName = member.roles.cache.some((role) => role.name === config.adminRoleName);
  const hasDiscordAdminPermission = member.permissions.has(PermissionsBitField.Flags.Administrator);

  return byRoleName || hasDiscordAdminPermission;
}

client.once("clientReady", async () => {
  logger.info(`Bot online as ${client.user.tag}`);
  await discordManager.sendLog("Admin bridge bot is online.");
});

client.on("messageCreate", async (message) => {
  if (message.author.bot || !message.guild || !message.content.startsWith(config.commandPrefix)) {
    return;
  }

  const body = message.content.slice(config.commandPrefix.length).trim();
  if (!body) {
    return;
  }

  const [rawCommand, ...args] = body.split(/\s+/);
  const commandName = rawCommand.toLowerCase();
  const command = commands.get(commandName);

  if (!command) {
    return;
  }

  if (command.adminOnly && !hasAdminRole(message.member)) {
    await message.reply(`You must have the ${config.adminRoleName} role to use this command.`);
    return;
  }

  try {
    await command.execute({
      message,
      args,
      apiClient,
      discordManager,
      config,
      logger
    });
  } catch (error) {
    logger.error(`Unhandled error while running command ${commandName}`, {
      message: error.message
    });
    await message.reply("Command failed due to an internal error.");
  }
});

let isPolling = false;
let cursor = undefined;

async function runPollTick() {
  if (isPolling) {
    return;
  }

  isPolling = true;
  try {
    // Poll backend changes so Discord reflects website/game-server events in near real-time.
    const payload = await apiClient.pollUpdates(cursor);
    const syncData = payload?.data || payload;

    if (syncData?.cursor) {
      cursor = syncData.cursor;
    }

    await discordManager.processSyncPayload(syncData);
  } catch (error) {
    logger.warn("Polling tick failed", { message: error.message });
  } finally {
    isPolling = false;
  }
}

setInterval(runPollTick, config.pollIntervalMs);

async function maybeRunSimulation() {
  if (!shouldSimulateDiscordPickup) {
    return;
  }

  if (!config.adminToken) {
    console.error("Missing SILVERSHADE_ADMIN_TOKEN for --simulate-discord-pickup");
    process.exit(1);
  }

  const payload = await apiClient.simulateDiscordPickup();
  const simData = payload?.data || payload;
  const confirmed = Number(simData?.confirmedActions ?? simData?.confirmed ?? simData?.count ?? 0);
  const message = String(simData?.message ?? "");
  const webhookSent = simData?.webhookSent === true;

  console.log(`confirmed: ${Number.isFinite(confirmed) ? confirmed : 0}`);
  console.log(`message: ${message}`);
  console.log(`webhookSent: ${webhookSent ? "true" : "false"}`);

  if (!webhookSent) {
    console.log("hint: backend needs DISCORD_TEST_WEBHOOK_URL set");
  }
}

maybeRunSimulation()
  .then(() => client.login(config.discordToken))
  .catch((error) => {
    logger.error("Startup failed", { message: error.message });
    process.exit(1);
  });

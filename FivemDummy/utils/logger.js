const fs = require('fs');
const path = require('path');

const LEVELS = {
  info: 'INFO',
  warn: 'WARN',
  error: 'ERROR',
  debug: 'DEBUG'
};

const logFilePath = path.resolve(process.cwd(), process.env.LOG_FILE_PATH || 'logs/server.log');
const logDirectory = path.dirname(logFilePath);

if (!fs.existsSync(logDirectory)) {
  fs.mkdirSync(logDirectory, { recursive: true });
}

function formatMessage(level, message, meta) {
  const timestamp = new Date().toISOString();
  const suffix = meta ? ` ${JSON.stringify(meta)}` : '';
  return `[${timestamp}] [${LEVELS[level] || 'LOG'}] ${message}${suffix}`;
}

function writeLog(level, message, meta) {
  const line = formatMessage(level, message, meta);
  fs.appendFile(logFilePath, `${line}\n`, () => {});

  if (level === 'error') {
    console.error(line);
    return;
  }

  if (level === 'warn') {
    console.warn(line);
    return;
  }

  if (level === 'debug') {
    console.debug(line);
    return;
  }

  console.log(line);
}

module.exports = {
  info(message, meta) {
    writeLog('info', message, meta);
  },
  warn(message, meta) {
    writeLog('warn', message, meta);
  },
  error(message, meta) {
    writeLog('error', message, meta);
  },
  debug(message, meta) {
    writeLog('debug', message, meta);
  }
};

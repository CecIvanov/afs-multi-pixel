// Structured JSON logger (TypeScript). Its output shape is byte-identical to the
// Python logger in packages/app_logger so a single log query joins the Node and
// Python services. Keep the two in lockstep — a parity test guards the shape.
//
//   { ts, level, event, context, message?, error? }

export type LogLevel = "debug" | "info" | "warn" | "error";
export type LogContext = Record<string, unknown>;

export type LogEntry = {
  ts: string;
  level: LogLevel;
  event: string;
  message?: string;
  context: LogContext;
  error?: { name: string; message: string; stack?: string };
};

export type LogTransport = (entry: LogEntry) => void;

export type LoggerOptions = {
  level?: LogLevel;
  transport?: LogTransport;
  baseContext?: LogContext;
};

const LEVEL_PRIORITY: Record<LogLevel, number> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
};

export function resolveLevel(value?: string): LogLevel {
  switch ((value ?? "").toLowerCase()) {
    case "debug":
    case "info":
    case "warn":
    case "error":
      return value!.toLowerCase() as LogLevel;
    default:
      return "info";
  }
}

export function consoleTransport(entry: LogEntry): void {
  const line = JSON.stringify(entry);
  if (entry.level === "error") console.error(line);
  else if (entry.level === "warn") console.warn(line);
  else console.log(line);
}

export class Logger {
  private readonly level: LogLevel;
  private readonly transport: LogTransport;
  private readonly baseContext: LogContext;

  constructor(options: LoggerOptions = {}) {
    this.level = options.level ?? resolveLevel(process.env.LOG_LEVEL);
    this.transport = options.transport ?? consoleTransport;
    this.baseContext = options.baseContext ?? {};
  }

  child(context: LogContext): Logger {
    return new Logger({
      level: this.level,
      transport: this.transport,
      baseContext: { ...this.baseContext, ...context },
    });
  }

  private log(level: LogLevel, event: string, context: LogContext, message?: string, error?: unknown): void {
    if (LEVEL_PRIORITY[level] < LEVEL_PRIORITY[this.level]) return;

    const entry: LogEntry = {
      ts: new Date().toISOString(),
      level,
      event,
      context: { ...this.baseContext, ...context },
    };
    if (message) entry.message = message;
    if (error instanceof Error) {
      entry.error = { name: error.name, message: error.message, stack: error.stack };
    } else if (error !== undefined) {
      entry.error = { name: "Error", message: String(error) };
    }
    this.transport(entry);
  }

  debug(event: string, context: LogContext = {}, message?: string): void {
    this.log("debug", event, context, message);
  }
  info(event: string, context: LogContext = {}, message?: string): void {
    this.log("info", event, context, message);
  }
  warn(event: string, context: LogContext = {}, message?: string): void {
    this.log("warn", event, context, message);
  }
  error(event: string, error: unknown, context: LogContext = {}, message?: string): void {
    this.log("error", event, context, message, error);
  }
}

export function createLogger(options: LoggerOptions = {}): Logger {
  return new Logger(options);
}

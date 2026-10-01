// Idempotent Prisma bootstrap for a SHARED Postgres (the backend's Alembic history
// owns every other table). Baselines the Session migration if the table already
// exists, then applies any pending Prisma migrations. Run by `npm run setup`.

import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { PrismaClient } from "@prisma/client";

export const SESSION_MIGRATION = "20240530213853_create_session_table";
const rootDir = join(dirname(fileURLToPath(import.meta.url)), "..");

export async function sessionTableExists(prisma) {
  const rows = await prisma.$queryRaw`
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'Session' LIMIT 1`;
  return Array.isArray(rows) && rows.length > 0;
}

export async function prismaMigrationApplied(prisma, migrationName = SESSION_MIGRATION) {
  try {
    const rows = await prisma.$queryRaw`
      SELECT 1 FROM "_prisma_migrations"
      WHERE migration_name = ${migrationName} AND finished_at IS NOT NULL LIMIT 1`;
    return Array.isArray(rows) && rows.length > 0;
  } catch {
    return false;
  }
}

function runPrisma(command) {
  execSync(command, { cwd: rootDir, stdio: "inherit" });
}

export async function ensurePrismaDatabase(prisma, { runCommand = runPrisma } = {}) {
  if (!(await prismaMigrationApplied(prisma))) {
    if (await sessionTableExists(prisma)) {
      // Table exists (created by ensure-session-table.sql or a prior deploy) but
      // Prisma has no record of it — baseline instead of failing migrate deploy.
      console.log("Session table present; baselining migration.");
      runCommand(`npx prisma migrate resolve --applied ${SESSION_MIGRATION}`);
    } else {
      const sql = readFileSync(join(rootDir, "prisma/ensure-session-table.sql"), "utf8");
      await prisma.$executeRawUnsafe(sql);
      runCommand(`npx prisma migrate resolve --applied ${SESSION_MIGRATION}`);
    }
  }
  console.log("Applying pending Prisma migrations...");
  runCommand("npx prisma migrate deploy");
}

// Run when invoked directly.
if (import.meta.url === `file://${process.argv[1]}`) {
  const prisma = new PrismaClient();
  ensurePrismaDatabase(prisma)
    .then(() => prisma.$disconnect())
    .catch(async (error) => {
      console.error("ensure-prisma-db failed:", error);
      await prisma.$disconnect();
      process.exit(1);
    });
}

-- AlterTable
ALTER TABLE "MarketPixel" ADD COLUMN "capiToken" TEXT;
ALTER TABLE "MarketPixel" ADD COLUMN "testEventCode" TEXT;

-- CreateTable
CREATE TABLE "ShopConfig" (
    "shop" TEXT NOT NULL PRIMARY KEY,
    "allowedHosts" TEXT NOT NULL,
    "updatedAt" DATETIME NOT NULL
);

-- CreateTable
CREATE TABLE "AppKey" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT DEFAULT 1,
    "publicKey" TEXT NOT NULL,
    "privateKey" TEXT NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- CreateTable
CREATE TABLE "PendingPurchase" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "shop" TEXT NOT NULL,
    "orderId" TEXT NOT NULL,
    "browser" TEXT,
    "order" TEXT,
    "sentAt" DATETIME,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL
);

-- CreateTable
CREATE TABLE "EventLog" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "shop" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "eventName" TEXT NOT NULL,
    "eventId" TEXT,
    "marketId" TEXT,
    "pixelId" TEXT,
    "status" TEXT NOT NULL,
    "detail" TEXT,
    "origin" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- CreateIndex
CREATE UNIQUE INDEX "PendingPurchase_shop_orderId_key" ON "PendingPurchase"("shop", "orderId");

-- CreateIndex
CREATE INDEX "EventLog_shop_createdAt_idx" ON "EventLog"("shop", "createdAt");

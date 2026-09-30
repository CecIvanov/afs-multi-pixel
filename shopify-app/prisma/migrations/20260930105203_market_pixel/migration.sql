-- CreateTable
CREATE TABLE "MarketPixel" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "shop" TEXT NOT NULL,
    "marketId" TEXT NOT NULL,
    "marketName" TEXT NOT NULL,
    "pixelId" TEXT NOT NULL,
    "updatedAt" DATETIME NOT NULL
);

-- CreateIndex
CREATE INDEX "MarketPixel_shop_idx" ON "MarketPixel"("shop");

-- CreateIndex
CREATE UNIQUE INDEX "MarketPixel_shop_marketId_key" ON "MarketPixel"("shop", "marketId");

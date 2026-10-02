import { useEffect, useState } from "react";
import { useRevalidator } from "react-router";
import { updatedAgo } from "../markets.shared.mjs";

/** "Updated N min ago", kept current while the page stays open. */
function useUpdatedLabel(loadedAt: string) {
  const [now, setNow] = useState(() => new Date(loadedAt));
  useEffect(() => {
    setNow(new Date());
    const timer = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(timer);
  }, [loadedAt]);
  return updatedAgo(loadedAt, now);
}

/** Reloads the page's data without a browser refresh (#15). */
export function RefreshButton({ loadedAt }: { loadedAt: string }) {
  const revalidator = useRevalidator();
  const label = useUpdatedLabel(loadedAt);
  return (
    <s-stack direction="inline" gap="small-200" alignItems="center">
      <s-text color="subdued">{label}</s-text>
      <s-button icon="refresh" loading={revalidator.state !== "idle"} onClick={() => revalidator.revalidate()}>
        Refresh
      </s-button>
    </s-stack>
  );
}

import { viberFabAnchorAttrs } from "../support.shared.mjs";
import styles from "../viber-fab.module.css";

type Props = {
  enabled: boolean;
  numberE164: string;
  label: string;
};

// Floating "Chat on Viber" button, mounted in the admin shell. Renders only when
// the merchant has enabled it (app.config.json support.viber.enabled) — otherwise
// nothing is shown.
export function ViberFab({ enabled, numberE164, label }: Props) {
  if (!enabled) return null;
  const attrs = viberFabAnchorAttrs(numberE164);
  return (
    <a className={styles.fab} aria-label={label} title={label} {...attrs}>
      <svg className={styles.icon} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M12 2C6.9 2 3 5.6 3 10.2c0 2.4 1.1 4.6 3 6.1v3.2c0 .5.6.8 1 .5l2.6-1.8c.8.2 1.6.3 2.4.3 5.1 0 9-3.6 9-8.2S17.1 2 12 2Zm3.9 11.4c-.2.5-.9.9-1.4 1-.4.1-.9.1-2.9-.8-2.4-1-4-3.5-4.1-3.7-.1-.2-1-1.3-1-2.4 0-1.1.6-1.7.8-1.9.2-.2.4-.3.6-.3h.4c.1 0 .3 0 .5.4l.6 1.5c.1.1.1.3 0 .5l-.3.4c-.1.2-.3.3-.1.5.1.2.6 1 1.3 1.6.9.8 1.6 1 1.8 1.1.2.1.4.1.5-.1l.5-.6c.2-.2.3-.2.5-.1l1.4.7c.2.1.4.2.4.3.1.1.1.5 0 .9Z" />
      </svg>
      <span className={styles.label}>{label}</span>
    </a>
  );
}

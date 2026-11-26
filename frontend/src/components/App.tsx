import { useMemo, useState } from "react";
import type { WidgetConfig } from "../config/config";
import { SessionManager } from "../services/session";
import { TurnstileClient } from "../services/turnstile";
import { ChatWindow } from "./ChatWindow";

interface Props {
  config: WidgetConfig;
  turnstileContainer: HTMLElement; // light-DOM element slotted into the shadow root
}

export function App({ config, turnstileContainer }: Props) {
  const [open, setOpen] = useState(false);
  const session = useMemo(() => {
    const turnstile = new TurnstileClient(turnstileContainer, config.turnstileSiteKey);
    return new SessionManager(config.apiUrl, () => turnstile.getToken());
  }, [config, turnstileContainer]);

  return (
    <div className={`root ${config.position}`} style={{ "--primary": config.primaryColor } as React.CSSProperties}>
      {open && <ChatWindow config={config} session={session} onClose={() => setOpen(false)} />}
      <button
        type="button"
        className="launcher"
        aria-label={open ? "Close chat" : "Chat with us"}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? (
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M4 5h16v11H9l-5 4z" />
          </svg>
        )}
      </button>
    </div>
  );
}

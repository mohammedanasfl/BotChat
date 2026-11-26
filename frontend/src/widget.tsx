/**
 * Embeddable entry point. Including this script (once or many times) adds ONE
 * <abinaya-chat> element to the page. React renders inside its Shadow DOM so the host site's
 * styles stay untouched; the Turnstile container stays in the light DOM and is slotted in.
 *
 *   <script src="https://<pages>/widget.js" data-api-url="…" data-turnstile-site-key="…" defer></script>
 */
import { createRoot } from "react-dom/client";
import { App } from "./components/App";
import { readConfig } from "./config/config";
import css from "./styles.css?inline";

const TAG = "abinaya-chat";
// Must be read while the script executes (it's null afterwards).
const config = readConfig(document.currentScript);

class AbinayaChatElement extends HTMLElement {
  connectedCallback() {
    if (this.shadowRoot) return; // already mounted (element moved in the DOM)
    const shadow = this.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = css;
    const mount = document.createElement("div");
    shadow.append(style, mount);

    const turnstileContainer = document.createElement("div");
    turnstileContainer.slot = "turnstile";
    this.appendChild(turnstileContainer);

    createRoot(mount).render(<App config={config} turnstileContainer={turnstileContainer} />);
  }
}

function mount() {
  if (!document.querySelector(TAG)) document.body.appendChild(document.createElement(TAG));
}

// Guard against the script being included more than once.
if (!customElements.get(TAG)) {
  customElements.define(TAG, AbinayaChatElement);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount, { once: true });
  else mount();
}

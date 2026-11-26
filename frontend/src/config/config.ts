/** Widget configuration: build-time defaults, overridable with data-* attributes on the script tag. */
export interface WidgetConfig {
  apiUrl: string;
  turnstileSiteKey: string;
  title: string;
  primaryColor: string;
  position: "right" | "left";
}

export function readConfig(script: HTMLOrSVGScriptElement | null): WidgetConfig {
  const data = script instanceof HTMLScriptElement ? script.dataset : {};
  return {
    apiUrl: (data.apiUrl || import.meta.env.VITE_API_URL || "").replace(/\/+$/, ""),
    turnstileSiteKey: data.turnstileSiteKey || import.meta.env.VITE_TURNSTILE_SITE_KEY || "",
    title: data.title || "Abinaya Garments",
    primaryColor: data.primaryColor || "#26335f",
    position: data.position === "left" ? "left" : "right",
  };
}

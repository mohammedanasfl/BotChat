/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  readonly VITE_TURNSTILE_SITE_KEY: string;
}

declare module "*.css?inline" {
  const css: string;
  export default css;
}

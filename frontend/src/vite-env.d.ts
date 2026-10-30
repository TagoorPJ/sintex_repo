/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend origin when it is not same-origin, e.g. https://greetings.example.com */
  readonly VITE_API_URL?: string;
}

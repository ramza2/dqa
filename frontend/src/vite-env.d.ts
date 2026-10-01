/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_DEV_PROXY_TARGET?: string;
  /** Local development only. Attached only when import.meta.env.DEV is true. */
  readonly VITE_DQA_DEV_ACTOR?: string;
  /** Local development only. Attached only when import.meta.env.DEV is true. */
  readonly VITE_DQA_DEV_ROLES?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

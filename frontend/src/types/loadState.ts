export interface LoadState {
  status: "idle" | "loading" | "ready" | "error" | "empty";
  message: string | null;
  code: string | null;
  httpStatus: number | null;
}

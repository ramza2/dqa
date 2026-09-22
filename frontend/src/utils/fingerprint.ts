export function shortenFingerprint(value: string, visible = 12): string {
  if (value.length <= visible + 3) {
    return value;
  }
  return `${value.slice(0, visible)}…`;
}

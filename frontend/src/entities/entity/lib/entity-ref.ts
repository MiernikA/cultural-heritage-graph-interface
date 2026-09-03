import type { EntityRef } from "@/shared/api";

export function isEntityRef(value: EntityRef | string): value is EntityRef {
  return typeof value !== "string";
}

export function shortUri(uri: string): string {
  return uri.split("#").pop()?.split("/").pop() ?? uri;
}

import {
  getActiveCatalog,
  listCategories,
  listRelations,
  listTables,
} from "./catalog";
import type {
  CatalogActiveSummary,
  CatalogCategoryItem,
  CatalogQueryEnvelope,
  CatalogRelationItem,
  CatalogTableItem,
} from "../types/catalog";
import { matchesActive } from "../utils/revision";

const PAGE_SIZE = 500;
const MAX_TABLES = 1000;
const MAX_RELATIONS = 2000;

export interface CatalogErdSnapshot {
  active: CatalogActiveSummary;
  tables: CatalogTableItem[];
  relations: CatalogRelationItem[];
  categories: CatalogCategoryItem[];
  totalTables: number;
  totalRelations: number;
  totalCategories: number;
  truncated: boolean;
}

function checkEnvelope<T>(
  response: CatalogQueryEnvelope<T>,
  active: CatalogActiveSummary,
  offset: number,
  limit: number,
  total: number | null,
) {
  if (response.source_name !== active.source_name ||
    !matchesActive(response, active, active.source_name) ||
    response.offset !== offset || response.limit !== limit ||
    !Number.isInteger(response.total) || response.total < 0 ||
    !Array.isArray(response.items) || response.items.length > limit ||
    offset + response.items.length > response.total ||
    (total !== null && response.total !== total) ||
    (response.items.length === 0 && offset < response.total)) {
    throw new Error("CATALOG_ERD_REVISION_OR_PAGE_MISMATCH");
  }
}

async function readBounded<T>(
  active: CatalogActiveSummary,
  maxItems: number,
  fetchPage: (offset: number, limit: number) => Promise<CatalogQueryEnvelope<T>>,
) {
  let offset = 0;
  let total: number | null = null;
  const items: T[] = [];
  do {
    const limit = Math.min(PAGE_SIZE, maxItems - offset);
    const response = await fetchPage(offset, limit);
    checkEnvelope(response, active, offset, limit, total);
    total = response.total;
    items.push(...response.items);
    offset += response.items.length;
  } while (offset < (total ?? 0) && offset < maxItems);

  return { items, total: total ?? 0, truncated: offset < (total ?? 0) };
}

/** Bounded, revision-pinned Catalog reads. No Oracle, Snapshot or write endpoints. */
export async function loadActiveCatalogErd(sourceName: string): Promise<CatalogErdSnapshot> {
  const active = await getActiveCatalog(sourceName);
  if (active.source_name !== sourceName || active.package_readiness !== "READY") {
    throw new Error("CATALOG_ERD_ACTIVE_NOT_READY");
  }
  const [tables, relations, categoriesResponse] = await Promise.all([
    readBounded(active, MAX_TABLES, (offset, limit) =>
      listTables(sourceName, { offset, limit })),
    readBounded(active, MAX_RELATIONS, (offset, limit) =>
      listRelations(sourceName, { offset, limit })),
    listCategories(sourceName, { offset: 0, limit: PAGE_SIZE }),
  ]);
  checkEnvelope(categoriesResponse, active, 0, PAGE_SIZE, null);
  const latestActive = await getActiveCatalog(sourceName);
  if (!matchesActive(active, latestActive, sourceName) ||
      latestActive.package_readiness !== "READY") {
    throw new Error("CATALOG_ERD_ACTIVE_CHANGED");
  }
  return {
    active,
    tables: tables.items,
    relations: relations.items,
    categories: categoriesResponse.items,
    totalTables: tables.total,
    totalRelations: relations.total,
    totalCategories: categoriesResponse.total,
    truncated: tables.truncated || relations.truncated ||
      categoriesResponse.items.length < categoriesResponse.total,
  };
}

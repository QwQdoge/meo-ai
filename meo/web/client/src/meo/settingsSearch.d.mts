type CatalogField = { id: string; label: string; labelKey: string };
type CatalogSection = { id: string; label: string; labelKey: string; items: readonly CatalogField[] };
export declare function matchSettingsSections<T extends CatalogSection>(
  sections: readonly T[], query: string,
  translate?: (key: string, fallback: string) => string,
): T[];

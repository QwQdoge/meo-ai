// Pure catalog search used by the Web settings renderer.
// The shared UI Schema remains the source of destinations and field identities.
export function matchSettingsSections(sections, query, translate = (_key, fallback) => fallback) {
  const needle = String(query || "").trim().toLocaleLowerCase();
  if (!needle) return sections;
  return sections.filter((section) => {
    const terms = [section.id, section.label, translate(section.labelKey, section.label), ...(section.keywords || [])];
    for (const item of section.items) {
      terms.push(item.id.replaceAll("_", " "), item.label,
        translate(item.labelKey, item.label));
    }
    return terms.some((value) => String(value).toLocaleLowerCase().includes(needle));
  });
}

.pragma library
.import "MeoUiSchema.js" as Schema

// This adapter maps semantic icon identities to the native MeoUI icon font.
// Placement, ordering and destination identity remain in the shared schema.
function destinations(placement) {
    const icons = {"chat":"chat_bubble", "work":"work", "projects":"folder_open", "skills":"extension", "settings":"tune"}
    return Schema.configuration.navigation.navigation.filter(function(item) {
        return item.placement === placement
    }).sort(function(a,b) { return a.order - b.order || a.id.localeCompare(b.id) }).map(function(item) {
        return {label: qsTranslate("MeoNavigation", item.label), icon: icons[item.icon] || "apps", action: item.id}
    })
}

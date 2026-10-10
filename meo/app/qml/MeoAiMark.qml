import QtQuick

// Compatibility shim for older call sites that still instantiate MeoAiMark.
// Keep the actual AI brand implementation in AiLogo.qml so the logo can be
// replaced globally without editing conversation/navigation layouts.
AiLogo {
    objectName: "meo.aiLogo.compat"
}

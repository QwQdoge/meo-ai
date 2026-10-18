use crate::capabilities::{
    CapabilityCatalog, CapabilityConnectionState, CapabilityDescriptor, CapabilityError,
    CapabilityKind, CapabilityOrigin,
};

/// Register capabilities shipped with Meo AI itself.
///
/// Built-in Skills describe reusable workflows only. They intentionally expose
/// no privileged tools; tools arrive from separately connected capabilities.
pub fn register_builtin_capabilities(
    catalog: &mut CapabilityCatalog,
) -> Result<(), CapabilityError> {
    catalog.upsert(system_diagnostics_skill())?;
    Ok(())
}

pub fn system_diagnostics_skill() -> CapabilityDescriptor {
    CapabilityDescriptor {
        capability_id: "skill.system-diagnostics".to_owned(),
        kind: CapabilityKind::Skill,
        label: "System diagnostics".to_owned(),
        description:
            "Diagnose MeoArch symptoms from observed facts and available typed capabilities."
                .to_owned(),
        origin: CapabilityOrigin::Builtin,
        provider: "Meo AI".to_owned(),
        icon: "diagnostics".to_owned(),
        enabled: true,
        configurable: true,
        connection_state: CapabilityConnectionState::NotRequired,
        permissions: vec![],
        tools: vec![],
        provides: vec![],
        requires: vec![],
        context_hint: concat!(
            "For system diagnostics, separate observed facts from hypotheses; ",
            "prefer registered read capabilities; propose the smallest repair and verification; ",
            "never treat a Skill as permission to execute a system action."
        )
        .to_owned(),
        tags: vec!["diagnostics".to_owned(), "system".to_owned()],
    }
}

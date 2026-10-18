plugins {
    id("com.android.application") version "9.4.0" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.10" apply false
}

// All durable generated output belongs outside the source checkout.
val meoOutputRoot = providers.environmentVariable("MEO_OUTPUT_ROOT")
    .orElse(rootDir.resolve("../../../outputs").canonicalPath)
layout.buildDirectory.set(file("${meoOutputRoot.get()}/meo-ai/build/android/root"))
subprojects {
    layout.buildDirectory.set(file("${meoOutputRoot.get()}/meo-ai/build/android/${project.name}"))
}

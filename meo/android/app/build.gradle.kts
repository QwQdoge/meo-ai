import org.gradle.api.tasks.Exec

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
}

val meoOAuthClientId = providers.gradleProperty("MEO_OAUTH_CLIENT_ID")
    .orElse(providers.environmentVariable("MEO_OAUTH_CLIENT_ID"))
    .orElse("org.meo.ai.android")
    .get()
val escapedOAuthClientId = meoOAuthClientId
    .replace("\\", "\\\\")
    .replace("\"", "\\\"")

android {
    namespace = "org.meo.ai"
    compileSdk = 36
    ndkVersion = "28.2.13676358"

    defaultConfig {
        applicationId = "org.meo.ai"
        minSdk = 28
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "MEO_OAUTH_CLIENT_ID", "\"$escapedOAuthClientId\"")
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

val rustOutput = layout.projectDirectory.dir("src/main/jniLibs")
val rustCrate = rootProject.layout.projectDirectory.dir("../core-rs")

fun registerRustBuild(name: String, release: Boolean) = tasks.register<Exec>(name) {
    workingDir(rustCrate.asFile)
    val args = mutableListOf(
        "cargo", "ndk",
        "-t", "arm64-v8a",
        "-t", "armeabi-v7a",
        "-t", "x86_64",
        "-o", rustOutput.asFile.absolutePath,
        "build",
        "--features", "android-jni",
    )
    if (release) args += "--release"
    commandLine(args)
}

val buildRustDebug = registerRustBuild("buildRustDebug", false)
val buildRustRelease = registerRustBuild("buildRustRelease", true)

tasks.matching { it.name == "preDebugBuild" }.configureEach { dependsOn(buildRustDebug) }
tasks.matching { it.name == "preReleaseBuild" }.configureEach { dependsOn(buildRustRelease) }

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2026.09.00")
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.material3:material3:1.5.0-beta01")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")

    implementation("io.coil-kt.coil3:coil-compose:3.6.3")
    implementation("io.coil-kt.coil3:coil-network-okhttp:3.6.3")

    debugImplementation("androidx.compose.ui:ui-tooling")
}

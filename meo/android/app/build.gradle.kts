import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.Exec
import org.gradle.process.ExecOperations
import javax.inject.Inject
import java.net.URI

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

// This is a trusted deployment origin, not a user-supplied URL or an OAuth secret.
// An absent origin keeps remote Work visibly unavailable instead of falling back
// to an arbitrary endpoint or pretending the device is enrolled.
val configuredAgentCloud = providers.gradleProperty("MEO_AGENT_CLOUD_URL")
    .orElse(providers.environmentVariable("MEO_AGENT_CLOUD_URL"))
    .orElse("").get().trim().trimEnd('/')
if (configuredAgentCloud.isNotEmpty()) {
    val origin = URI(configuredAgentCloud)
    require(origin.scheme == "https" && !origin.host.isNullOrBlank() &&
        origin.userInfo == null && origin.rawPath.isNullOrEmpty() &&
        origin.rawQuery == null && origin.rawFragment == null) {
        "MEO_AGENT_CLOUD_URL must be an HTTPS origin without paths or credentials"
    }
}
val escapedAgentCloud = configuredAgentCloud.replace("\\", "\\\\").replace("\"", "\\\"")

android {
    namespace = "org.meo.ai"
    compileSdk = 37
    ndkVersion = "28.2.13676358"

    defaultConfig {
        applicationId = "org.meo.ai"
        minSdk = 28
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "MEO_OAUTH_CLIENT_ID", "\"$escapedOAuthClientId\"")
        buildConfigField("String", "MEO_AGENT_CLOUD_URL", "\"$escapedAgentCloud\"")
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

abstract class GenerateMeoUiSchema : DefaultTask() {
    @get:InputDirectory abstract val schemaRoot: DirectoryProperty
    @get:OutputDirectory abstract val outputDirectory: DirectoryProperty
    @get:Inject abstract val execOperations: ExecOperations

    @TaskAction
    fun generate() {
        execOperations.exec {
            commandLine(
                "node",
                schemaRoot.file("generate.mjs").get().asFile.absolutePath,
                "--output",
                outputDirectory.get().asFile.absolutePath,
            )
        }
    }
}

val generateUiSchema = tasks.register<GenerateMeoUiSchema>("generateMeoUiSchema") {
    schemaRoot.set(rootProject.layout.projectDirectory.dir("../ui-schema"))
    outputDirectory.set(layout.buildDirectory.dir("generated/ui-schema"))
}
androidComponents {
    onVariants(selector().all()) { variant ->
        // AGP 9 requires generated sources to be registered via the Variant API.
        // The output contains kotlin/MeoUiSchema.kt plus non-source metadata.
        variant.sources.java?.addGeneratedSourceDirectory(
            generateUiSchema, GenerateMeoUiSchema::outputDirectory,
        )
    }
}

val rustOutput = layout.buildDirectory.dir("generated/jniLibs")
// JNI libs are built in preDebugBuild/preReleaseBuild below; pass a concrete
// filesystem path instead of an unsupported Provider<Directory> source entry.
android.sourceSets.getByName("main").jniLibs.srcDir(rustOutput.get().asFile)

val rustCrate = rootProject.layout.projectDirectory.dir("../core-rs")

fun registerRustBuild(name: String, release: Boolean) = tasks.register<Exec>(name) {
    workingDir(rustCrate.asFile)
    environment("CARGO_BUILD_JOBS", providers.environmentVariable("CARGO_BUILD_JOBS").orElse("1").get())
    environment("CARGO_TARGET_DIR", layout.buildDirectory.dir("rust-target").get().asFile.absolutePath)
    val args = mutableListOf(
        "cargo", "ndk",
        "-t", "arm64-v8a",
        "-t", "armeabi-v7a",
        "-t", "x86_64",
        "-o", rustOutput.get().asFile.absolutePath,
        "build", "--locked",
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

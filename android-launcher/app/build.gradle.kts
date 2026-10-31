plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

val sotcAndroid = providers.gradleProperty("sotcAndroid").orNull == "true"
val bionicRuntime = providers.gradleProperty("gow3Bionic").orNull == "true" || sotcAndroid

android {
    namespace = "com.gow3.android"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "com.gow3.android"
        minSdk = 28
        targetSdk = 28
        versionCode = 2010604
        versionName = "2.1.6-daedalus.4"
        manifestPlaceholders["appLabel"] = "@string/app_name"
        manifestPlaceholders["appIcon"] = "@drawable/icon"
        if (bionicRuntime) {
            applicationId = "com.gow3.android.bionic"
            minSdk = 30
            versionName = "2.1.6-daedalus.4-bionic"
            manifestPlaceholders["appLabel"] = "God of War III — Daedalus Fork"
            if (sotcAndroid) {
                applicationId = "com.sotc.android.daedalus"
                versionCode = 10007
                versionName = "0.1.6-boot-test"
                manifestPlaceholders["appIcon"] = "@drawable/sotc_icon"
                manifestPlaceholders["appLabel"] = "Shadow of the Colossus — Daedalus"
            }
        }

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            optimization {
                enable = false
            }
        }
    }
    splits {
        abi {
            isEnable = true
            reset()
            include("arm64-v8a")
            isUniversalApk = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    lint {
        // targetSdk 28 是本移植的硬性运行约束（Android 不变量）；它是
        // 侧载的游戏 APK，而非 Play Store 提交。
        disable += "ExpiredTargetSdkVersion"
    }
    buildFeatures {
        compose = true
    }
    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
    }
    sourceSets {
        getByName("main") {
            jniLibs.srcDir("../../tools/android/bridges")
            if (bionicRuntime) jniLibs.srcDir("../../out/bionic/apk-jni")
        }
        getByName("debug") {
            assets.srcDir("../../out/android-debug/assets")
        }
        getByName("release") {
            assets.srcDir("../../out/android-release/assets")
        }
    }
}

// 调试运行时 payload 不是源文件：它由仓库工具生成。
// 在任何 debug 构建之前（幂等地）暂存它，以便 Android Studio 一键构建携带
// 匹配的无游戏运行时，与 tools/android/debug/build_debug_apk.sh 的做法一致。
val stageDebugRuntime by tasks.registering(Exec::class) {
    workingDir = rootProject.projectDir.parentFile
    commandLine("bash", "tools/android/debug/stage_debug_runtime.sh")
    // 没有可靠的 up-to-date 输入：总是重新执行（运行时缓存新鲜时很快）。
    outputs.upToDateWhen { false }
}
tasks.matching { it.name == "preDebugBuild" }.configureEach {
    dependsOn(stageDebugRuntime)
}

dependencies {
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    testImplementation(libs.junit)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    debugImplementation(libs.androidx.compose.ui.tooling)

}

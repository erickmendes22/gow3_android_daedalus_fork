plugins {
    alias(libs.plugins.android.application)
}

android {
    namespace = "ro.cobrabm.fexdroid"
    compileSdk {
        version = release(37)
    }
    defaultConfig {
        applicationId = "com.daedalus.order1886"
        minSdk = 30
        targetSdk = 30
        versionCode = 20
        versionName = "0.1.18-gpu-perf-signed"
    }
    // Stable signing for upgrade-in-place. Keystore and password are injected by CI
    // secrets; never put private signing material in the public source tree.
    val persistentKey = System.getenv("ORDER1886_KEYSTORE_FILE")
    val persistentPassword = System.getenv("ORDER1886_KEYSTORE_PASSWORD")
    if (!persistentKey.isNullOrBlank() && !persistentPassword.isNullOrBlank()) {
        signingConfigs {
            create("persistent") {
                storeFile = file(persistentKey)
                storePassword = persistentPassword
                keyAlias = "order1886"
                keyPassword = persistentPassword
                storeType = "pkcs12"
            }
        }
    }
    buildTypes {
        release {
            optimization { enable = false }
            if (!persistentKey.isNullOrBlank() && !persistentPassword.isNullOrBlank()) {
                signingConfig = signingConfigs.getByName("persistent")
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
    sourceSets {
        getByName("main") {
            java.srcDir("../../the-order-1886-android/overlay/android-launcher/app/src/main/java")
            jniLibs.srcDir("../../out/order1886/apk-jni")
            assets.srcDir("../../out/order1886/apk-assets")
        }
    }
    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    lint { disable += "ExpiredTargetSdkVersion" }
}

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
        versionCode = 15
        versionName = "0.1.13-adreno840-msaa-restart"
    }
    buildTypes {
        release {
            optimization { enable = false }
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

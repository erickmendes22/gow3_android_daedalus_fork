pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        // Maven Central intermittently returned 404 for published Kotlin
        // artifacts (including kotlin-stdlib and the plugin BOM) on CI.
        // Keep normal upstream sources and add independent fallback mirrors.
        mavenCentral()
        maven(url = "https://maven.aliyun.com/repository/central")
        maven(url = "https://maven.aliyun.com/repository/gradle-plugin")
        gradlePluginPortal()
    }
}
// CI provisions JDK 25 before Gradle starts; no remote JDK resolver is needed.
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        maven(url = "https://maven.aliyun.com/repository/google")
        maven(url = "https://maven.aliyun.com/repository/central")
    }
}

rootProject.name = "Gow3Launcher"
include(":app")

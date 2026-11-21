pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
        // Fallback for transient Maven Central outages on GitHub runners.
        maven(url = "https://maven-central.storage-download.googleapis.com/maven2/")
        maven(url = "https://repo1.maven.org/maven2/")
    }
}
plugins {
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        maven(url = "https://maven-central.storage-download.googleapis.com/maven2/")
        maven(url = "https://repo1.maven.org/maven2/")
    }
}

rootProject.name = "Gow3Launcher"
include(":app")
include(":order1886")

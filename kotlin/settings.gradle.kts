rootProject.name = "pgm-kotlin"

// reference: normalization, features and later the computation, as they go into the app
// baseline:  the app's dictionary (app-snapshot/) as the baseline for comparison
include("reference", "baseline")

dependencyResolutionManagement {
    repositories { mavenCentral() }
}

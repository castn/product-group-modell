plugins {
    kotlin("jvm")
    application
}

kotlin { jvmToolchain(25) }

// The app's code lives (not yet versioned) in ../app-snapshot. The app's test needs
// ReceiptParser and fixtures that are missing here, hence only the classification.
sourceSets.main {
    kotlin.srcDir("../app-snapshot")
    kotlin.exclude("**/*Test.kt")
}

application { mainClass.set("BaselineKt") }

plugins {
    kotlin("jvm")
    application
}

kotlin { jvmToolchain(25) }

// The app's code is a fixed copy in ../app-snapshot (origin in SOURCE). The app's test needs
// ReceiptParser and fixtures that are missing here, hence only the classification.
sourceSets.main {
    kotlin.srcDir("../app-snapshot")
    kotlin.exclude("**/*Test.kt")
}

application { mainClass.set("BaselineKt") }

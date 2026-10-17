plugins {
    kotlin("jvm")
}

kotlin { jvmToolchain(25) }

dependencies {
    testImplementation(kotlin("test"))
}

tasks.test {
    useJUnitPlatform()
    // golden values live in the Python part of the repo
    systemProperty("golden.dir", rootDir.resolve("../tests/golden").absolutePath)
    systemProperty("dist.dir", rootDir.resolve("../dist").absolutePath)
    testLogging { showStandardStreams = true }
}

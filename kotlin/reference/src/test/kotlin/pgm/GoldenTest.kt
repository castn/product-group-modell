package pgm

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** Checks against tests/golden/ in the Python part, so that both implementations compute the same */
class GoldenTest {

    private val dir = File(System.getProperty("golden.dir"))

    private fun rows(file: String) = File(dir, file).readLines()
        .filter { it.isNotEmpty() && !it.startsWith("#") }
        .map { line -> line.split('\t').map(::unescape) }

    private fun unescape(s: String) = buildString {
        var i = 0
        while (i < s.length) {
            if (s[i] == '\\' && i + 1 < s.length) {
                append(
                    when (s[i + 1]) {
                        't' -> '\t'
                        'n' -> '\n'
                        '\\' -> '\\'
                        else -> error("unknown escape in $s")
                    }
                )
                i += 2
            } else {
                append(s[i++])
            }
        }
    }

    @Test
    fun normalize() {
        val cases = rows("normalize.tsv")
        assertTrue(cases.isNotEmpty())
        for ((raw, expected) in cases) {
            assertEquals(expected, Normalize.normalize(raw), "input: $raw")
        }
    }

    @Test
    fun fnvReferenceVectors() {
        assertEquals(0x811C9DC5u, Features.fnv1a32(ByteArray(0)))
        assertEquals(0xE40C292Cu, Features.fnv1a32("a".toByteArray()))
        assertEquals(0xBF9CF968u, Features.fnv1a32("foobar".toByteArray()))
    }

    @Test
    fun features() {
        val configs = mapOf(
            "default" to FeatureConfig(),
            "small" to FeatureConfig(buckets = 1000, minn = 3, maxn = 4, bigrams = false, store = false),
        )
        val cases = rows("features.tsv")
        assertTrue(cases.size > 50)
        for ((config, name, store, ids) in cases) {
            val expected = if (ids.isEmpty()) emptyList() else ids.split(',').map(String::toInt)
            val actual = Features.ids(name, store.ifEmpty { null }, configs.getValue(config)).toList()
            assertEquals(expected, actual, "$config: $name / $store")
        }
    }
}

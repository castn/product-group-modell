package pgm

import java.io.File
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Computes like the Python reference (src/pgm/export.py): probabilities within tolerance,
 * order of the best classes and chain of the store exactly.
 */
class ModelGoldenTest {

    private val golden = File(System.getProperty("golden.dir"))
    private val dist = File(System.getProperty("dist.dir"))

    private fun unescape(s: String) = s.replace("\\t", "\t").replace("\\n", "\n").replace("\\\\", "\\")

    private fun check(model: ProductGroupModel, tsv: File) {
        val rows = tsv.readLines().filter { it.isNotEmpty() && !it.startsWith("#") }
        assertTrue(rows.isNotEmpty())
        for (line in rows) {
            val (rawName, rawStore, chain, margin, top) = line.split('\t')
            val name = unescape(rawName)
            val store = unescape(rawStore).ifEmpty { null }
            assertEquals(chain.ifEmpty { null }, model.chainOf(store), "chain: $store")
            val p = model.probabilities(name, store)
            if (top.isEmpty()) {
                assertNull(p, "no features expected: $name")
                continue
            }
            val expected = top.split(',').map { it.split('=').let { (c, v) -> c to v.toFloat() } }
            for ((cls, prob) in expected) {
                val actual = p!![model.classes.indexOf(cls)]
                assertTrue(abs(actual - prob) <= 1e-5f, "$name / $cls: $actual instead of $prob")
            }
            if (margin.toFloat() >= 1e-4f) {
                assertEquals(expected.map { it.first }, model.topK(name, store, expected.size).map { it.first }, name)
            }
        }
    }

    @Test
    fun tinyModel() {
        val model = ProductGroupModel.load(File(golden, "tiny.pgm").readBytes())
        assertEquals("tiny-1", model.version)
        assertEquals(listOf("produce", "produce", "dairy", "dairy", "household", "alcohol"), model.groups)
        check(model, File(golden, "tiny.tsv"))
    }

    /** Exported models from dist/, if present (not in the repo) */
    @Test
    fun exportedModels() {
        val models = dist.listFiles { f -> f.name.endsWith(".bin") }.orEmpty()
        for (bin in models) {
            val tsv = File(bin.path.removeSuffix(".bin") + ".golden.tsv")
            if (!tsv.exists()) continue
            val model = ProductGroupModel.load(bin.readBytes())
            check(model, tsv)
            val names = tsv.readLines().filter { !it.startsWith("#") }.map { it.substringBefore('\t') }
            repeat(3) { names.forEach { model.classify(it, "REWE") } } // warm-up
            val start = System.nanoTime()
            val rounds = 20
            repeat(rounds) { names.forEach { model.classify(it, "REWE") } }
            val micros = (System.nanoTime() - start) / 1000.0 / (rounds * names.size)
            println("${bin.name}: ${model.classes.size} classes, golden values match, %.0f µs per row".format(micros))
        }
    }

    @Test
    fun classifyUsesThresholds() {
        val model = ProductGroupModel.load(File(golden, "tiny.pgm").readBytes())
        // The random model is never sure: probabilities around 1/6
        assertNull(model.classify("Bio Vollmilch", "REWE"))
        assertNull(model.classify("🍓"))
        assertTrue(model.topK("Bio Vollmilch", k = 6).size == 6)
    }

    @Test
    fun corruptFileIsRejected() {
        val data = File(golden, "tiny.pgm").readBytes()
        data[100] = (data[100].toInt() xor 1).toByte()
        assertFailsWith<IllegalArgumentException> { ProductGroupModel.load(data) }
    }
}

package pgm

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.zip.CRC32
import kotlin.math.exp

enum class Level { SURE, SUGGESTION }

/**
 * @param classId fine class of the model, e.g. "pflanzendrinks"
 * @param groupId ItemGroup.id of the app, e.g. "dairy"
 */
data class GroupPrediction(
    val classId: String,
    val groupId: String,
    val confidence: Float,
    val level: Level,
)

/**
 * Model in the format of src/pgm/export.py (docs/interface.md). Reads the file once and
 * then computes without further allocations apart from small arrays per call.
 */
class ProductGroupModel private constructor(
    val version: String,
    val created: Long,
    val features: FeatureConfig,
    private val dim: Int,
    private val temperature: Float,
    val thresholdSure: Float,
    val thresholdSuggest: Float,
    val classes: List<String>,
    val groups: List<String>,
    private val chains: List<String>,
    private val aliases: List<Pair<String, Int>>,
    private val scales: FloatArray,
    private val embedding: ByteArray,
    private val output: FloatArray,
    private val bias: FloatArray,
) {

    /** null if the confidence is below the suggestion threshold or the name has no features */
    fun classify(itemName: String, store: String? = null): GroupPrediction? {
        val p = probabilities(itemName, store) ?: return null
        var best = 0
        for (k in 1 until p.size) if (p[k] > p[best]) best = k
        val confidence = p[best]
        val level = when {
            confidence >= thresholdSure -> Level.SURE
            confidence >= thresholdSuggest -> Level.SUGGESTION
            else -> return null
        }
        return GroupPrediction(classes[best], groups[best], confidence, level)
    }

    /** The k most likely classes, descending; empty without features */
    fun topK(itemName: String, store: String? = null, k: Int = 3): List<Pair<String, Float>> {
        val p = probabilities(itemName, store) ?: return emptyList()
        return p.indices.sortedWith(compareByDescending<Int> { p[it] }.thenBy { it })
            .take(k).map { classes[it] to p[it] }
    }

    /** Chain for a store name, like pgm.stores.lookup */
    fun chainOf(store: String?): String? {
        if (store.isNullOrEmpty()) return null
        val text = Normalize.normalize(store.replace('-', ' '))
        val words = text.split(' ').toSet()
        for ((alias, index) in aliases) {
            if (alias in words || text == alias || text.startsWith("$alias ")) return chains[index]
        }
        return null
    }

    /** Probability per class in the order of [classes]; null without features */
    fun probabilities(itemName: String, store: String? = null): FloatArray? {
        val ids = Features.ids(itemName, chainOf(store), features)
        if (ids.isEmpty()) return null
        val h = FloatArray(dim)
        for (id in ids) {
            val scale = scales[id]
            val row = id * dim
            for (d in 0 until dim) h[d] += embedding[row + d] * scale
        }
        val n = ids.size.toFloat()
        for (d in 0 until dim) h[d] /= n
        val z = FloatArray(classes.size)
        var max = Float.NEGATIVE_INFINITY
        for (k in classes.indices) {
            var logit = bias[k]
            val row = k * dim
            for (d in 0 until dim) logit += output[row + d] * h[d]
            z[k] = logit / temperature
            if (z[k] > max) max = z[k]
        }
        var sum = 0f
        for (k in z.indices) {
            z[k] = exp(z[k] - max)
            sum += z[k]
        }
        for (k in z.indices) z[k] /= sum
        return z
    }

    companion object {
        private const val FORMAT = 1

        fun load(data: ByteArray): ProductGroupModel {
            require(data.size > 8) { "file too short" }
            val crc = CRC32().apply { update(data, 0, data.size - 4) }.value
            val buffer = ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN)
            require(buffer.getInt(data.size - 4).toUInt().toLong() == crc) { "CRC does not match" }
            buffer.limit(data.size - 4)

            fun u8() = buffer.get().toInt() and 0xFF
            fun u16() = buffer.getShort().toInt() and 0xFFFF
            fun string(length: Int) = ByteArray(length).also { buffer.get(it) }.toString(Charsets.UTF_8)

            val magic = ByteArray(4).also { buffer.get(it) }
            require(magic.contentEquals("PGM1".toByteArray())) { "not a PGM model" }
            val format = u16()
            require(format == FORMAT) { "format $format not supported" }
            val version = string(u16())
            val created = buffer.getLong()
            val buckets = buffer.getInt()
            val dim = u16()
            val minn = u8()
            val maxn = u8()
            val flags = u16()
            val temperature = buffer.getFloat()
            val sure = buffer.getFloat()
            val suggest = buffer.getFloat()
            val classes = mutableListOf<String>()
            val groups = mutableListOf<String>()
            repeat(u16()) {
                classes += string(u8())
                groups += string(u8())
            }
            val chains = List(u16()) { string(u8()) }
            val aliases = List(u16()) { string(u8()) to u16() }
            val scales = FloatArray(buckets).also { buffer.asFloatBuffer().get(it) }
            buffer.position(buffer.position() + 4 * buckets)
            val embedding = ByteArray(buckets * dim).also { buffer.get(it) }
            val output = FloatArray(classes.size * dim).also { buffer.asFloatBuffer().get(it) }
            buffer.position(buffer.position() + 4 * output.size)
            val bias = FloatArray(classes.size).also { buffer.asFloatBuffer().get(it) }
            buffer.position(buffer.position() + 4 * bias.size)
            require(!buffer.hasRemaining()) { "data after the end" }

            val features = FeatureConfig(
                buckets = buckets, minn = minn, maxn = maxn,
                bigrams = flags and 1 != 0, store = flags and 2 != 0,
            )
            return ProductGroupModel(
                version, created, features, dim, temperature, sure, suggest, classes, groups,
                chains, aliases, scales, embedding, output, bias,
            )
        }
    }
}

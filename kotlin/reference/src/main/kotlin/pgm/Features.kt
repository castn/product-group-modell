package pgm

/**
 * fastText-style features per docs/interface.md. Must return the same features in the same
 * order as src/pgm/features.py, checked via tests/golden/features.tsv.
 */
data class FeatureConfig(
    val buckets: Int = 1 shl 16,
    val minn: Int = 2,
    val maxn: Int = 5,
    val bigrams: Boolean = true,
    val store: Boolean = true,
)

object Features {

    private const val FNV_OFFSET = 0x811C9DC5u
    private const val FNV_PRIME = 0x01000193u

    fun fnv1a32(data: ByteArray): UInt {
        var h = FNV_OFFSET
        for (b in data) {
            h = h xor (b.toUInt() and 0xFFu)
            h *= FNV_PRIME
        }
        return h
    }

    /**
     * Units, price and tax markers that the receipt parser leaves on the name
     * ("BANANE 0,750 KG X 1,79 EUR KG"); they only dilute the mean of the features.
     */
    private val SKIP_TOKENS = setOf("X", "KG", "G", "L", "ML", "EUR", "ST", "STK", "STUECK", "AW", "A", "B")
    private const val NUMERIC = "0123456789,.%-"

    /** Words of the normalized name without pure numbers and without [SKIP_TOKENS] */
    fun tokens(name: String): List<String> =
        Normalize.normalize(name).split(' ').filter { token ->
            token.isNotEmpty() && token !in SKIP_TOKENS && !token.all { it in NUMERIC }
        }

    /** Duplicates are not removed (like fastText) */
    fun strings(name: String, store: String?, cfg: FeatureConfig): List<String> {
        val tokens = tokens(name)
        val features = mutableListOf<String>()
        for (token in tokens) {
            val word = "<$token>"
            features += word
            for (n in cfg.minn..cfg.maxn) {
                for (i in 0..word.length - n) {
                    val gram = word.substring(i, i + n)
                    if (gram != word) features += gram
                }
            }
        }
        if (cfg.bigrams) tokens.zipWithNext { a, b -> features += "$a $b" }
        if (cfg.store && store != null && tokens.isNotEmpty()) {
            val storeNorm = Normalize.normalize(store)
            if (storeNorm.isNotEmpty()) features += "__store=$storeNorm"
        }
        return features
    }

    fun ids(name: String, store: String?, cfg: FeatureConfig): IntArray =
        strings(name, store, cfg)
            .map { (fnv1a32(it.toByteArray(Charsets.UTF_8)) % cfg.buckets.toUInt()).toInt() }
            .toIntArray()
}

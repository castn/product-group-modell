package pgm

import java.text.Normalizer

/**
 * Normalization of item names per docs/interface.md. Must be identical char by char to
 * src/pgm/normalize.py, checked via tests/golden/normalize.tsv.
 *
 * The result contains only A–Z, 0–9, `% , . - ! &` and single spaces.
 */
object Normalize {

    // Replace before decomposition, otherwise "Ä" would become just "A"
    private val special = mapOf(
        'ä' to "ae", 'Ä' to "AE",
        'ö' to "oe", 'Ö' to "OE",
        'ü' to "ue", 'Ü' to "UE",
        'ß' to "ss", 'ẞ' to "SS",
        'æ' to "ae", 'Æ' to "AE",
        'œ' to "oe", 'Œ' to "OE",
        'ø' to "o", 'Ø' to "O",
    )

    private const val ALLOWED_PUNCTUATION = "%,.-!& "

    fun normalize(text: String): String {
        val composed = Normalizer.normalize(text, Normalizer.Form.NFKC)
        val replaced = buildString { composed.forEach { append(special[it] ?: it) } }
        val decomposed = Normalizer.normalize(replaced, Normalizer.Form.NFKD)
        val result = StringBuilder(decomposed.length)
        var lastSpace = true // do not write leading spaces in the first place
        var i = 0
        while (i < decomposed.length) {
            val cp = decomposed.codePointAt(i)
            i += Character.charCount(cp)
            if (Character.getType(cp) == Character.NON_SPACING_MARK.toInt()) continue
            // Deliberately only a–z, not uppercase(): Java and Python differ in special cases
            val c = if (cp in 'a'.code..'z'.code) cp - 32 else cp
            val allowed = c in 'A'.code..'Z'.code || c in '0'.code..'9'.code ||
                (c < 128 && ALLOWED_PUNCTUATION.indexOf(c.toChar()) >= 0)
            if (allowed && c != ' '.code) {
                result.append(c.toChar())
                lastSpace = false
            } else if (!lastSpace) {
                result.append(' ')
                lastSpace = true
            }
        }
        return result.trimEnd().toString()
    }
}

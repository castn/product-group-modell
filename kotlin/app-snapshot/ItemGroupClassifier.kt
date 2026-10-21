package org.totschnig.myexpenses.next.receipts

import org.totschnig.myexpenses.db2.productKey
import org.totschnig.myexpenses.model2.ReceiptItem
import java.text.Normalizer

/** Where the group of an item comes from */
enum class ItemGroupSource {
    /** Fixed rules: deposit, and discounts take the group of their item */
    RULE,

    /** The user chose the group for the same product before */
    PRODUCT,

    /** Words of products the user chose groups for */
    WORDS,

    /** [ItemDictionary] */
    DICTIONARY,

    /** The kind of shop, e.g. a drugstore, for items no other source knows */
    MERCHANT
}

data class ItemGroupSuggestion(val group: ItemGroup, val source: ItemGroupSource)

/** A group the user chose for an item, to learn from */
data class LearnedItemGroup(val name: String, val group: ItemGroup)

/**
 * Assigns groups to the items of a receipt without asking. Items no source knows stay without
 * group, the user can set them in the review.
 *
 * @param learned choices of the user, oldest first, so that the latest choice for a product wins
 */
class ItemGroupClassifier(learned: List<LearnedItemGroup>) {

    private val products: Map<String, ItemGroup> = learned.associate { productKey(it.name) to it.group }

    private val wordGroups: Map<String, List<ItemGroup>> = learned
        .flatMap { item -> ItemWords.of(item.name).distinct().map { it to item.group } }
        .groupBy({ it.first }, { it.second })

    /**
     * @param merchant the shop, from the receipt or the payee of the transaction
     * @return one suggestion per item, null if no source knows the item
     */
    fun classify(items: List<ReceiptItem>, merchant: String?): List<ItemGroupSuggestion?> {
        val merchantGroup = merchant?.let(::groupOfMerchant)
        val result = mutableListOf<ItemGroupSuggestion?>()
        items.forEachIndexed { index, item ->
            result += classify(item, merchantGroup) { discountGroup(items, result, index) }
        }
        return result
    }

    private fun classify(
        item: ReceiptItem,
        merchantGroup: ItemGroup?,
        discountGroup: () -> ItemGroup?
    ): ItemGroupSuggestion? {
        val words = ItemWords.of(item.name)
        if (words.any { word -> DEPOSIT_WORDS.any { word.startsWith(it) } }) {
            return ItemGroupSuggestion(ItemGroup.DEPOSIT, ItemGroupSource.RULE)
        }
        if (item.amount < 0) {
            return discountGroup()?.let { ItemGroupSuggestion(it, ItemGroupSource.RULE) }
        }
        products[productKey(item.name)]?.let { return ItemGroupSuggestion(it, ItemGroupSource.PRODUCT) }
        byWords(words)?.let { return ItemGroupSuggestion(it, ItemGroupSource.WORDS) }
        byDictionary(words)?.let { return ItemGroupSuggestion(it, ItemGroupSource.DICTIONARY) }
        return merchantGroup?.let { ItemGroupSuggestion(it, ItemGroupSource.MERCHANT) }
    }

    /**
     * A discount belongs to the item it names ("Feigen 1 Euro" after the total), otherwise to the
     * item above ("Preisänderung")
     */
    private fun discountGroup(items: List<ReceiptItem>, groups: List<ItemGroupSuggestion?>, index: Int): ItemGroup? {
        val words = ItemWords.of(items[index].name)
        val named = (index - 1 downTo 0).firstOrNull { earlier ->
            items[earlier].amount > 0 && ItemWords.of(items[earlier].name).any { candidate ->
                words.any { ItemWords.sameStem(it, candidate) }
            }
        }
        val item = named ?: (index - 1 downTo 0).firstOrNull { items[it].amount > 0 }
        return item?.let { groups[it]?.group }
    }

    /** Words seen with mostly one group; the one seen most often wins */
    private fun byWords(words: List<String>): ItemGroup? =
        words.mapNotNull { word ->
            val groups = wordGroups[word]?.takeIf { it.size >= MIN_WORD_COUNT } ?: return@mapNotNull null
            groups.groupingBy { it }.eachCount().maxBy { it.value }
                .takeIf { it.value >= groups.size * MIN_WORD_SHARE }
                ?.let { it.key to it.value }
        }.maxByOrNull { it.second }?.first

    /**
     * The best keyword match of all words: strong keywords before weak ones, then the closer kind
     * of match, then the longer keyword, then the earlier word, as receipts print the product
     * before its variant ("Joghurt Erdbeere")
     */
    private fun byDictionary(words: List<String>): ItemGroup? =
        words.flatMapIndexed { index, word ->
            ItemDictionary.keywords.mapNotNull { keyword ->
                ItemWords.match(word, keyword)?.let { quality -> Match(keyword, quality, index) }
            }
        }.maxWithOrNull(
            compareBy<Match> { !it.keyword.isWeak }
                .thenBy { it.quality }
                .thenBy { it.keyword.word.length }
                .thenByDescending { it.index }
        )?.keyword?.group

    private class Match(val keyword: ItemDictionary.Keyword, val quality: Int, val index: Int)

    private fun groupOfMerchant(merchant: String): ItemGroup? {
        val words = ItemWords.fold(merchant).split(" ")
        return MERCHANTS.entries.firstOrNull { (_, names) ->
            names.any { name -> words.any { it == name || (name.length >= 5 && it.startsWith(name)) } }
        }?.key
    }

    companion object {
        /** A word needs to have been chosen this often, and mostly with one group */
        private const val MIN_WORD_COUNT = 2
        private const val MIN_WORD_SHARE = 0.8

        private val DEPOSIT_WORDS = listOf("pfand", "leergut")

        /** Kinds of shops whose items mostly belong to one group, folded like [ItemWords.fold] */
        private val MERCHANTS = mapOf(
            ItemGroup.DRUGSTORE to listOf("dm", "rossmann", "mueller", "drogerie", "budnikowsky", "apotheke"),
            ItemGroup.PET to listOf("fressnapf", "zooplus", "futterhaus", "zoo"),
            ItemGroup.NON_FOOD to listOf("obi", "hornbach", "bauhaus", "toom", "hagebau", "baumarkt"),
            ItemGroup.BAKERY to listOf("baecker", "baeckerei", "backhaus", "backstube", "backwerk"),
            ItemGroup.MEAT_FISH to listOf("metzger", "metzgerei", "fleischerei", "fischhandel"),
            ItemGroup.DRINKS to listOf("getraenke", "getraenkemarkt"),
        )
    }
}

/** Words of item names on receipts, independent of case, umlauts and abbreviation dots */
internal object ItemWords {

    /** "Grünl.Sch.Räuch." → "gruenl sch raeuch" */
    fun fold(text: String): String = Normalizer.normalize(
        text.lowercase().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss"),
        Normalizer.Form.NFD
    ).replace(Regex("\\p{M}"), "").replace(Regex("[^a-z]+"), " ").trim()

    /**
     * Words that can tell the kind of goods: no units, sizes and filler words, nothing after "mit",
     * as it names an ingredient ("Laugenzopf m. Käse")
     */
    fun of(name: String): List<String> {
        val words = fold(name).split(" ").flatMap { word ->
            // Recognition sometimes misses the space before "mit"
            if (word.length >= 7 && word.endsWith("mit")) listOf(word.dropLast(3), "mit") else listOf(word)
        }
        val ingredients = words.indexOfFirst { it in INGREDIENT_MARKERS }
        return (if (ingredients > 0) words.subList(0, ingredients) else words)
            .filter { it.length >= MIN_LENGTH && it !in STOP_WORDS }
    }

    /**
     * How [word] matches [keyword], higher is closer: 3 same word, 2 end of a joined word
     * ("grillkaese"), 1 shortened keyword ("schlagsah"), 0 start of a joined word ("laugenzopf"),
     * -1 one letter misread ("zwieaeln")
     */
    fun match(word: String, keyword: ItemDictionary.Keyword): Int? {
        val key = keyword.word
        return when {
            word == key -> 3
            keyword.wholeWordOnly -> null
            key.length >= 4 && word.endsWith(key) -> 2
            word.length >= 5 && key.startsWith(word) -> 1
            key.length >= 5 && word.startsWith(key) -> 0
            minOf(word.length, key.length) >= MIN_MISREAD_LENGTH && oneEditApart(word, key) -> -1
            else -> null
        }
    }

    /** One letter replaced, added or missing */
    private fun oneEditApart(a: String, b: String): Boolean {
        if (kotlin.math.abs(a.length - b.length) > 1) return false
        var i = 0
        while (i < a.length && i < b.length && a[i] == b[i]) i++
        return when {
            a.length == b.length -> a.substring(i + 1) == b.substring(i + 1)
            a.length > b.length -> a.substring(i + 1) == b.substring(i)
            else -> a.substring(i) == b.substring(i + 1)
        }
    }

    /** "feigen" and "feige" */
    fun sameStem(a: String, b: String) = minOf(a.length, b.length) >= 4 && (a.startsWith(b) || b.startsWith(a))

    private const val MIN_LENGTH = 3
    private const val MIN_MISREAD_LENGTH = 6
    private val INGREDIENT_MARKERS = setOf("m", "mit")
    private val STOP_WORDS = setOf(
        "bio", "und", "der", "die", "das", "fuer", "aus", "von", "mix", "neu", "stk", "stueck", "pack", "packung",
        "euro", "eur", "ml", "kg",
        // Adjectives, which as shortened keywords would name other goods ("frisch" → "Frischhaltefolie")
        "frisch", "frische", "rot", "rote", "gruen", "gelb", "weiss", "schwarz", "fein", "grob", "klein", "gross",
        "natur", "classic", "original", "leicht", "light"
    )
}

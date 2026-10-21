package org.totschnig.myexpenses.next.receipts

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.totschnig.myexpenses.feature.recognizedTextFromJson
import org.totschnig.myexpenses.model2.ReceiptItem
import org.totschnig.myexpenses.next.receipts.ItemGroup.BAKERY
import org.totschnig.myexpenses.next.receipts.ItemGroup.DAIRY
import org.totschnig.myexpenses.next.receipts.ItemGroup.DEPOSIT
import org.totschnig.myexpenses.next.receipts.ItemGroup.DRINKS
import org.totschnig.myexpenses.next.receipts.ItemGroup.DRUGSTORE
import org.totschnig.myexpenses.next.receipts.ItemGroup.HOUSEHOLD
import org.totschnig.myexpenses.next.receipts.ItemGroup.MEAT_FISH
import org.totschnig.myexpenses.next.receipts.ItemGroup.PANTRY
import org.totschnig.myexpenses.next.receipts.ItemGroup.PRODUCE
import org.totschnig.myexpenses.next.receipts.ItemGroup.READY_MEALS
import org.totschnig.myexpenses.next.receipts.ItemGroupSource.DICTIONARY
import org.totschnig.myexpenses.next.receipts.ItemGroupSource.MERCHANT
import org.totschnig.myexpenses.next.receipts.ItemGroupSource.PRODUCT
import org.totschnig.myexpenses.next.receipts.ItemGroupSource.RULE
import org.totschnig.myexpenses.next.receipts.ItemGroupSource.WORDS

class ItemGroupClassifierTest {

    private val classifier = ItemGroupClassifier(emptyList())

    private fun item(name: String, amount: Long = 100) = ReceiptItem(name, amount)

    private fun ItemGroupClassifier.groupOf(name: String, merchant: String? = null) =
        classify(listOf(item(name)), merchant).single()

    @Test
    fun joinedAndShortenedWords() {
        assertEquals(ItemGroupSuggestion(DAIRY, DICTIONARY), classifier.groupOf("GAZI H.GRILLKAESE"))
        assertEquals(DAIRY, classifier.groupOf("G&G SCHLAGSAH")?.group)
        assertEquals(HOUSEHOLD, classifier.groupOf("G&G TOILETTENPAP.")?.group)
        assertEquals(PANTRY, classifier.groupOf("HAFERFL. KERNIG")?.group)
        // the end of a joined word names the kind
        assertEquals(PANTRY, classifier.groupOf("Kürbiskerne")?.group)
        assertEquals(DRINKS, classifier.groupOf("Apfelsaft naturtrüb")?.group)
    }

    @Test
    fun flavourAndIngredientDoNotDecide() {
        assertEquals(DAIRY, classifier.groupOf("Joghurt Erdbeere")?.group)
        assertEquals(READY_MEALS, classifier.groupOf("Burek Käse")?.group)
        assertEquals(BAKERY, classifier.groupOf("Laugenzopf m. Käse")?.group)
        assertEquals(BAKERY, classifier.groupOf("Strudelmit Kirschen")?.group)
        assertEquals(PANTRY, classifier.groupOf("SCHOKO MUESLI")?.group)
        assertEquals(PRODUCE, classifier.groupOf("PAPRIKA ROT")?.group)
    }

    @Test
    fun misreadLetter() {
        assertEquals(PRODUCE, classifier.groupOf("ZWIEAELN ROT")?.group)
        assertEquals(MEAT_FISH, classifier.groupOf("Leberurst frisch")?.group)
    }

    @Test
    fun wholeWordOnly() {
        assertNull(classifier.groupOf("Vollkorn"))
        assertEquals(ItemGroup.ALCOHOL, classifier.groupOf("Korn")?.group)
        // "wein" ends "Schwein", the longer keyword wins
        assertEquals(MEAT_FISH, classifier.groupOf("Hausschwein")?.group)
    }

    @Test
    fun depositAndDiscounts() {
        val groups = classifier.classify(
            listOf(
                item("FRISCHE FEIGE", 312), item("SCHW.FRISCHMILCH", 358), item("Preisänderung", -178),
                item("PFAND 0,25", 25), item("LEERGUT", -25), item("Feigen 1 Euro", -112)
            ),
            merchant = null
        )
        assertEquals(
            listOf(
                ItemGroupSuggestion(PRODUCE, DICTIONARY), ItemGroupSuggestion(DAIRY, DICTIONARY),
                // the item above
                ItemGroupSuggestion(DAIRY, RULE),
                ItemGroupSuggestion(DEPOSIT, RULE), ItemGroupSuggestion(DEPOSIT, RULE),
                // the item it names
                ItemGroupSuggestion(PRODUCE, RULE)
            ),
            groups
        )
    }

    @Test
    fun merchantForUnknownItems() {
        assertEquals(ItemGroupSuggestion(DRUGSTORE, MERCHANT), classifier.groupOf("Haarspange Glitzer", "dm-drogerie markt"))
        assertEquals(ItemGroupSuggestion(PANTRY, DICTIONARY), classifier.groupOf("dmBio Leinsamen", "dm-drogerie markt"))
        assertNull(classifier.groupOf("Haarspange Glitzer", "REWE"))
    }

    @Test
    fun learnedProductWinsOverDictionary() {
        val learning = ItemGroupClassifier(
            listOf(LearnedItemGroup("Meggle Baguet", BAKERY), LearnedItemGroup("MEGGLE BAGUET", READY_MEALS))
        )
        // the latest choice, independent of case and punctuation
        assertEquals(ItemGroupSuggestion(READY_MEALS, PRODUCT), learning.groupOf("Meggle Baguet."))
    }

    @Test
    fun learnedWordsNeedSeveralChoices() {
        val once = ItemGroupClassifier(listOf(LearnedItemGroup("Sportness Riegel", ItemGroup.SWEETS_SNACKS)))
        assertNull(once.groupOf("Sportness NatEnergy"))
        val twice = ItemGroupClassifier(
            listOf(
                LearnedItemGroup("Sportness Riegel", ItemGroup.SWEETS_SNACKS),
                LearnedItemGroup("Sportness Proteinriegel", ItemGroup.SWEETS_SNACKS)
            )
        )
        assertEquals(ItemGroupSuggestion(ItemGroup.SWEETS_SNACKS, WORDS), twice.groupOf("Sportness NatEnergy"))
    }

    private class Labelled(val receipt: String, val item: ReceiptItem, val expected: ItemGroup)

    /** Merchants of the fixtures whose photos were cut to the items */
    private val merchants = mapOf(
        "dm" to "dm-drogerie markt", "metzger" to "Metzgerei", "baecker" to "Bäckerei", "baumarkt" to "Baumarkt"
    )

    private fun labelled(): Map<String, Pair<String?, List<Labelled>>> {
        val labels = javaClass.getResource("/receipts/item-groups.csv")!!.readText().lines().drop(1)
            .filter { it.isNotBlank() }
            .map { line -> line.split(";").let { (receipt, name, group) -> Triple(receipt, name, ItemGroup.ofId(group)!!) } }
        return labels.groupBy { it.first }.mapValues { (receipt, rows) ->
            val parsed = ReceiptParser.parse(
                recognizedTextFromJson(javaClass.getResource("/receipts/$receipt.json")!!.readText())
            )
            val expected = rows.associate { it.second to it.third }
            (merchants[receipt] ?: parsed.merchant) to parsed.items.map { item ->
                Labelled(receipt, item, expected[item.name] ?: error("No label for ${item.name} in $receipt"))
            }
        }
    }

    private class Result(val total: Int, val assigned: Int, val correct: Int, val errors: List<String>)

    private fun evaluate(classifierFor: (String) -> ItemGroupClassifier): Result {
        var total = 0
        var assigned = 0
        var correct = 0
        val errors = mutableListOf<String>()
        for ((receipt, value) in labelled()) {
            val (merchant, items) = value
            val groups = classifierFor(receipt).classify(items.map { it.item }, merchant)
            items.zip(groups).forEach { (labelled, suggestion) ->
                total++
                if (suggestion != null) assigned++
                if (suggestion?.group == labelled.expected) correct++
                else errors += "$receipt: ${labelled.item.name} → ${suggestion?.group} (${suggestion?.source}), expected ${labelled.expected}"
            }
        }
        return Result(total, assigned, correct, errors)
    }

    private fun Result.report(title: String) {
        println("$title: $correct of $total correct (${correct * 100 / total} %), $assigned assigned (${assigned * 100 / total} %)")
        errors.forEach { println("  $it") }
    }

    /**
     * Built-in knowledge only, as for a new user. Optimistic: the dictionary was written knowing
     * these receipts.
     */
    @Test
    fun labelledReceiptsWithoutLearning() {
        val result = evaluate { classifier }
        result.report("Without learning")
        assertTrue(result.correct >= result.total * 0.85)
    }

    /** Each receipt with the choices of all other receipts learned, as for a user after some weeks */
    @Test
    fun labelledReceiptsLearnedFromOthers() {
        val all = labelled()
        val result = evaluate { receipt ->
            ItemGroupClassifier(
                all.filterKeys { it != receipt }.values.flatMap { it.second }
                    .map { LearnedItemGroup(it.item.name, it.expected) }
            )
        }
        result.report("Learned from the other receipts")
        assertTrue(result.correct >= result.total * 0.85)
    }
}

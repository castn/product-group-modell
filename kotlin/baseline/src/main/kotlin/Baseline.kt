import org.totschnig.myexpenses.model2.ReceiptItem
import org.totschnig.myexpenses.next.receipts.ItemGroupClassifier

/**
 * Applies the app's dictionary to item names.
 *
 * Input (stdin):   name<TAB>merchant   (merchant may be empty)
 * Output (stdout): group<TAB>source    (empty if no source knows the item)
 *
 * Each item is classified on its own, i.e. without the rule for discounts, which needs
 * the item above. Discounts are not part of the model's task.
 */
fun main() {
    val classifier = ItemGroupClassifier(emptyList())
    val out = System.out.bufferedWriter()
    System.`in`.bufferedReader().forEachLine { line ->
        val parts = line.split('\t')
        val merchant = parts.getOrNull(1)?.ifEmpty { null }
        val suggestion = classifier.classify(listOf(ReceiptItem(parts[0], 100)), merchant).single()
        out.write("${suggestion?.group?.id.orEmpty()}\t${suggestion?.source?.name.orEmpty()}\n")
    }
    out.flush()
}

// Stand-ins for the parts of the app that ItemGroupClassifier needs but that are not
// in app-snapshot/. This is enough for the baseline without learned products:
// productKey is only used for learned products, and the list is empty.

package org.totschnig.myexpenses.model2

data class ReceiptItem(val name: String, val amount: Long)

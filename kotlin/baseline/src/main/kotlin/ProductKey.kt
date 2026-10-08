package org.totschnig.myexpenses.db2

import org.totschnig.myexpenses.next.receipts.ItemWords

/** Stand-in for the app's productKey (only relevant with learned products) */
internal fun productKey(name: String): String = ItemWords.fold(name)

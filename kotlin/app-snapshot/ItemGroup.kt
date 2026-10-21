package org.totschnig.myexpenses.next.receipts

/**
 * Kind of goods of an item on a receipt, a level below the category of the transaction: the
 * category says what the purchase was for (e.g. Lebensmittel), the group what was in it.
 * Groups are by content, not by storage, so frozen peas are [PRODUCE].
 *
 * @param id stored in the database, never change it
 */
enum class ItemGroup(val id: String) {
    PRODUCE("produce"),
    BAKERY("bakery"),
    DAIRY("dairy"),
    MEAT_FISH("meat_fish"),
    PANTRY("pantry"),

    /** Ready meals and delicatessen, e.g. pizza, hummus, warm snacks */
    READY_MEALS("ready_meals"),
    SWEETS_SNACKS("sweets_snacks"),

    /** Without alcohol, with coffee and tea */
    DRINKS("drinks"),
    ALCOHOL("alcohol"),
    TOBACCO("tobacco"),
    DRUGSTORE("drugstore"),
    HOUSEHOLD("household"),
    PET("pet"),
    BABY("baby"),
    NON_FOOD("non_food"),
    DEPOSIT("deposit"),

    /** Chosen by the user for items that fit no other group, unlike items without group */
    OTHER("other");

    companion object {
        fun ofId(id: String?) = entries.firstOrNull { it.id == id }
    }
}

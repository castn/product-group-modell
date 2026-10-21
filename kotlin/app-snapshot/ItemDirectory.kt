package org.totschnig.myexpenses.next.receipts

import org.totschnig.myexpenses.next.receipts.ItemGroup.ALCOHOL
import org.totschnig.myexpenses.next.receipts.ItemGroup.BABY
import org.totschnig.myexpenses.next.receipts.ItemGroup.BAKERY
import org.totschnig.myexpenses.next.receipts.ItemGroup.DAIRY
import org.totschnig.myexpenses.next.receipts.ItemGroup.DRINKS
import org.totschnig.myexpenses.next.receipts.ItemGroup.DRUGSTORE
import org.totschnig.myexpenses.next.receipts.ItemGroup.HOUSEHOLD
import org.totschnig.myexpenses.next.receipts.ItemGroup.MEAT_FISH
import org.totschnig.myexpenses.next.receipts.ItemGroup.NON_FOOD
import org.totschnig.myexpenses.next.receipts.ItemGroup.PANTRY
import org.totschnig.myexpenses.next.receipts.ItemGroup.PET
import org.totschnig.myexpenses.next.receipts.ItemGroup.PRODUCE
import org.totschnig.myexpenses.next.receipts.ItemGroup.READY_MEALS
import org.totschnig.myexpenses.next.receipts.ItemGroup.SWEETS_SNACKS
import org.totschnig.myexpenses.next.receipts.ItemGroup.TOBACCO

/**
 * Built-in German words of goods. Receipts shorten names ("SCHLAGSAH", "HAFERFL.") and German
 * joins words ("Grillkäse"), so words also match as end of a word, and shortened words match
 * the start of a keyword, see [ItemWords.match].
 *
 * A keyword starting with "~" is weak: it usually names a flavour or ingredient ("Erdbeer
 * Joghurt", "Burek Käse"), so another keyword in the name wins. A keyword starting with "="
 * only matches the whole word, e.g. "korn", which ends "Vollkorn".
 */
internal object ItemDictionary {

    private val entries: Map<ItemGroup, String> = mapOf(
        // Fruit and vegetables are often the flavour of a product, so all of them are weak
        PRODUCE to """
            ~obst ~gemüse ~apfel ~äpfel ~banane ~bananen ~birne ~birnen ~orange ~orangen ~mandarine ~mandarinen
            ~clementine ~clementinen ~zitrone ~zitronen ~limette ~limetten ~erdbeere ~erdbeeren ~himbeere ~himbeeren
            ~heidelbeere ~heidelbeeren ~blaubeere ~blaubeeren ~johannisbeere ~kirsche ~kirschen ~trauben ~weintrauben
            ~pfirsich ~nektarine ~aprikose ~aprikosen ~pflaume ~pflaumen ~zwetschge ~mango ~ananas ~kiwi ~melone
            ~wassermelone ~feige ~feigen ~datteln ~granatapfel ~avocado ~rhabarber ~kartoffel ~kartoffeln
            ~süßkartoffel ~tomate ~tomaten ~gurke ~gurken ~paprika ~spitzpaprika ~zucchini ~aubergine ~karotte ~karotten ~möhre
            ~möhren ~zwiebel ~zwiebeln ~knoblauch ~lauch ~porree ~sellerie ~fenchel ~brokkoli ~broccoli ~blumenkohl
            ~kohlrabi ~weißkohl ~rotkohl ~grünkohl ~spinat ~salat ~rucola ~champignon ~champignons ~pilze ~radieschen
            ~rettich ~ingwer ~kräuter ~petersilie ~basilikum ~schnittlauch ~spargel ~=mais ~erbsen ~bohnen ~kürbis
            ~suppengrün ~bete
        """,
        BAKERY to """
            brot brötchen semmel semmeln baguette baguet toast toastbrot kuchen torte croissant croissants brezel
            breze brezn laugenstange zopf krusti kruste ciabatta fladenbrot tortilla wraps muffin muffins donut berliner
            krapfen strudel plunder schnecke streusel hörnchen knäckebrot knäcke zwieback prebake aufbackbrötchen
            stollen hefezopf
        """,
        DAIRY to """
            milch frischmilch vollmilch sahne schlagsahne schmand fraiche quark speisequark joghurt jogurt yoghurt
            skyr kefir buttermilch butter margarine ~käse gouda emmentaler edamer mozzarella =feta hirtenkäse parmesan
            camembert =brie frischkäse weichkäse hartkäse grillkäse halloumi obazda ricotta mascarpone grünländer
            leerdammer exquisa philadelphia altenburger grilltaler eier milchreis pudding
        """,
        MEAT_FISH to """
            fleisch hackfleisch gehacktes rind rinder schwein hähnchen huhn pute puten =ente wurst bratwurst
            leberwurst blutwurst ~leber salami schinken speck kassler wiener würstchen frikadelle frikadellen schnitzel
            steak gulasch filet braten lachs thunfisch hering forelle fisch garnelen shrimps fischstäbchen aufschnitt
            leberkäse mortadella chorizo
        """,
        PANTRY to """
            mehl zucker =salz pfeffer gewürz öl olivenöl sonnenblumenöl rapsöl essig nudeln spaghetti penne fusilli
            pasta =reis basmati couscous bulgur quinoa haferflocken flocken müsli musli cornflakes linsen kichererbsen
            konserve tomatenmark passata ketchup senf mayonnaise sauce soße brühe bouillon ~honig marmelade konfitüre
            nutella erdnussbutter mandeln haselnüsse haselnuss walnüsse walnuss cashew cashewkerne kerne samen leinsamen
            sesam chia hanfsamen kürbiskerne sonnenblumenkerne hefe hefewürfel backpulver vanillezucker puderzucker
            rosinen
        """,
        READY_MEALS to """
            pizza lasagne fertiggericht feinkost hummus kartoffelsalat nudelsalat fleischsalat eiersalat tortellini
            ravioli suppe eintopf burger döner burek börek pommes kroketten tzatziki sandwich
        """,
        SWEETS_SNACKS to """
            schokolade ~schoko riegel keks kekse cookies chips flips gummibärchen fruchtgummi bonbon bonbons lakritz
            praline pralinen waffel waffeln speiseeis eiscreme kaugummi popcorn salzstangen cracker marzipan lebkuchen
            spekulatius dominosteine
        """,
        DRINKS to """
            wasser mineralwasser sprudel saft apfelsaft orangensaft direktsaft nektar schorle limo limonade cola eistee
            =tee kaffee espresso cappuccino ~kakao smoothie energydrink drink isodrink sirup prisecco eiswürfel
        """,
        ALCOHOL to """
            bier pils pilsener weizen weißbier radler wein rotwein weißwein sekt prosecco champagner likör schnaps
            wodka vodka whisky whiskey =rum =gin =korn aperol dornfelder riesling grauburgunder spätburgunder merlot
            cabernet pinot chardonnay sauvignon primitivo tempranillo lambrusco glühwein cider
        """,
        TOBACCO to """
            zigarette zigaretten tabak drehtabak zigarre zigarren zigarillo zigarillos
        """,
        DRUGSTORE to """
            shampoo spülung duschgel duschbad seife handseife zahnpasta zahncreme zahnbürste zahnseide deo deodorant
            ~creme lotion bodylotion sonnencreme sonnenspray pumpspray rasierer rasierschaum tampons binden slipeinlagen
            watte wattepads wattestäbchen pflaster wundspray haargummis haargummi haarspray haargel mascara lippenstift
            nagellack balea nivea mivolis ebelin sundance alverde isana tabletten vitamine kondome
        """,
        HOUSEHOLD to """
            toilettenpapier klopapier küchenrolle küchenpapier taschentücher servietten frischhaltefolie alufolie
            backpapier gefrierbeutel müllbeutel müllsack spülmittel spülmaschinentabs waschmittel weichspüler reiniger
            allzweckreiniger glasreiniger schwamm schwämme kerzen batterien
        """,
        PET to """
            katzenfutter hundefutter tierfutter futter katzenstreu leckerli kauknochen whiskas sheba pedigree frolic
        """,
        BABY to """
            windeln feuchttücher babynahrung babybrei pampers babylove hipp alete
        """,
        NON_FOOD to """
            schraube schrauben dübel nägel kabel lampe socken strümpfe spielzeug zeitschrift zeitung blumenerde
        """,
    )

    class Keyword(val word: String, val group: ItemGroup, val isWeak: Boolean, val wholeWordOnly: Boolean)

    val keywords: List<Keyword> = entries.flatMap { (group, words) ->
        words.trim().split(Regex("\\s+")).map { raw ->
            val isWeak = raw.startsWith("~")
            val unmarked = raw.removePrefix("~")
            Keyword(ItemWords.fold(unmarked.removePrefix("=")), group, isWeak, unmarked.startsWith("="))
        }
    }
}

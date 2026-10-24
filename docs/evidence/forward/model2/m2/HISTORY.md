# S544 M2 read-out HISTORY (mode: production)

Calibration read-out only: Brier of arm M2 (the landed S542 staleness backstop with frozen constants, nothing fit) and of arm A on identical outcome rows and settlement. Every number is vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's. No statement about the venue.

age = our receipt age (state receipt minus used book receipt), not venue staleness; fresh <= 15 s < stale

prereg seal 936fb8fb6d3d539e978773b8c75be2d6eddfd5b766f3a643287f68b701fd2121; effective date 2026-10-01

## Headline (cumulative class live, segment all, age stale; delta = M2 - A Brier)

| sport | verdict | games | ticks | mean delta | CI lo | CI hi | nights not read out | descriptive | note | label |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mlb | INSUFFICIENT | 11 | 6001 | -0.009601602751054208799532985202 | -0.028726328296626247 | 0.011967575241136445 | 0 | True | MLB is INSUFFICIENT by declaration in this row | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | INSUFFICIENT | 10 | 3564 | -0.1048664208008015547678190831 | -0.16387178395157007 | -0.04146164119679512 | 0 | False | - | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | INSUFFICIENT | 3 | 1948 | 0E-8 | 0.0 | 0.0 | 0 | True | M2 is not defined for this sport (M2 = A) | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | INSUFFICIENT | 8 | 2600 | 0E-8 | 0.0 | 0.0 | 0 | True | M2 is not defined for this sport (M2 = A) | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |

## Nights dated on or after the effective date

| date | status |
| --- | --- |
| 2026-10-02 | scored |
| 2026-10-03 | scored |
| 2026-10-04 | scored |
| 2026-10-05 | scored |
| 2026-10-06 | scored |
| 2026-10-07 | scored |
| 2026-10-08 | scored |
| 2026-10-09 | scored |
| 2026-10-10 | scored |
| 2026-10-12 | scored |
| 2026-10-16 | scored |
| 2026-10-19 | scored |
| 2026-10-20 | scored |
| 2026-10-21 | scored |
| 2026-10-22 | scored |

## Entries

2026-10-02: night LF sha256 67de94d4699f9b51acc151d0dc3041432a10fe4e7b95a03cd83d1f00655266da; games 2
2026-10-03: night LF sha256 77d791e9d8c8b2de1dbd34c13ce0a3ec0a6b24d437795be86d3da0eec9da48cd; games 3
2026-10-04: night LF sha256 1fbdc7839882d47127d6279570bcdc39670707e683416f861768e9f495121c88; games 5
2026-10-05: night LF sha256 455cb236ea33b30828980cdeea6acf7cb85f34c1db9c803715bbd194715af16f; games 1
2026-10-06: night LF sha256 23a93c367c68da5629406aacd00c866906720a15aae7b7caf7a95c5cddcc9f4c; games 3
2026-10-07: night LF sha256 17a736f786f94fab2e476613fd8b8a2162c6893815b725bf5e10722f7e085f46; games 7
2026-10-08: night LF sha256 f4ad9f34452ed280cfed0a4110d4ff4f074386af8f5bab4478b9d1a73659685e; games 19
2026-10-09: night LF sha256 40afcdcbc80f3059e575b5d2ab3f902e979cc63b77d4a2445ea33f612804f6b1; games 19
2026-10-10: night LF sha256 9abc3a350e0c998e1a6df6f8bfc35de3f0f8601e60910c22e4ad7ea2bb9690f3; games 26
2026-10-12: night LF sha256 2fc082eb11324b3829804376ed6323e8ce8fca5976f7dabeb3ee8d10c1bd3e1b; games 7
2026-10-16: night LF sha256 abada2579648b41a3790af5ea68fa4ce0a158297fa6fe501ef5a9490330871c3; games 9
2026-10-19: night LF sha256 ed5fb8fb3937adb97891c8dcf36bc62a1d8fc72aabdefc20553b8d58042260eb; games 3
2026-10-20: night LF sha256 838e228a8c304ce12194441209c5bc5ba7730fca2b62fa890d856703a5ddc56b; games 4
2026-10-21: night LF sha256 c14c101b758836bcd010bc2d0bbdf6784b64ff5d6ef2c4b6bdb760863391ed18; games 7
2026-10-22: night LF sha256 0dc245cb2d82f47ab03b31c793173e431a150ce8dfe9f9837ebef274e4483cf1; games 3

## Cumulative cells (non-empty)

| sport | class | segment | age | ticks | games | mean A Brier | mean M2 Brier | mean M2 - A | CI lo | CI hi | label |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mlb | live | early | fresh | 3917 | 12 | 0.3107124904263466938983916262 | 0.3107124904263466938983916262 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | early | stale | 1246 | 11 | 0.2804636637239165329052969502 | 0.2920246243977092389380797992 | 0.01156096067379270603278284863 | -0.004364842573148044 | 0.04184501830337053 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | early | all | 5163 | 12 | 0.3034124636839047065659500291 | 0.3062024999030690900090736825 | 0.002790036219164383443123654734 | -0.001138844842009625 | 0.010001221360583549 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | middle | fresh | 1289 | 11 | 0.3170945888285492629945694337 | 0.3170945888285492629945694337 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | middle | stale | 3093 | 8 | 0.1760201665050113158745554478 | 0.1753805441531498561193066879 | -0.0006396223518614597552487594025 | -0.019068207404248062 | 0.018643073081358513 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | middle | all | 4382 | 11 | 0.2175183249657690552259242355 | 0.2170668525937226163799670438 | -0.0004514723720464388459571914267 | -0.013287441942235544 | 0.013508322669911817 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | late | fresh | 875 | 8 | 0.03403437142857142857142857143 | 0.03403437142857142857142857143 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | late | stale | 1662 | 7 | 0.07892435318892900120336943442 | 0.03677885188067718188937397079 | -0.04214550130825181931399546369 | -0.0923844643708062 | -0.009935199889378606 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | late | all | 2537 | 9 | 0.06344199842333464722112731573 | 0.03583229279688036117467068957 | -0.02760970562645428604645662619 | -0.06214506255302441 | -0.0038223518616198712 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | all | fresh | 6081 | 12 | 0.2722538768294688373622759415 | 0.2722538768294688373622759415 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | all | stale | 6001 | 11 | 0.1708149266788868521913014498 | 0.1612133239278326433917684645 | -0.009601602751054208799532985202 | -0.028726328296626247 | 0.011967575241136445 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | all | all | 12082 | 12 | 0.2218702367157755338520112564 | 0.2171012234639069436346633462 | -0.004769013251868590217347909634 | -0.014833847839446766 | 0.005914006140410245 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | pre_live | all | fresh | 74 | 7 | 0.3003760135135135135135135135 | 0.3003760135135135135135135135 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | pre_live | all | stale | 3963 | 8 | 0.2798383926318445622003532677 | 0.2798383926318445622003532677 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | pre_live | all | all | 4037 | 8 | 0.2802148563289571463958384939 | 0.2802148563289571463958384939 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | early | fresh | 45 | 3 | 0.2379538888888888888888888889 | 0.2379538888888888888888888889 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | early | stale | 91 | 1 | 0.25502500 | 0.25502500 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | early | all | 136 | 3 | 0.2493764705882352941176470588 | 0.2493764705882352941176470588 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | middle | stale | 12 | 2 | 0.40217500 | 0.3983981747466517199076235176 | -0.0037768252533482800923764821 | -0.2754311555193396 | 0.020919022952650933 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | middle | all | 12 | 2 | 0.40217500 | 0.3983981747466517199076235176 | -0.0037768252533482800923764821 | -0.2754311555193396 | 0.020919022952650933 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | late | stale | 35 | 6 | 0.04500785714285714285714285714 | 0.02911287722148992177737119409 | -0.01589497992136722107977166306 | -0.020905770428357135 | -0.0005710691666039165 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | late | all | 35 | 6 | 0.04500785714285714285714285714 | 0.02911287722148992177737119409 | -0.01589497992136722107977166306 | -0.020905770428357135 | -0.0005710691666039165 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | all | fresh | 45 | 3 | 0.2379538888888888888888888889 | 0.2379538888888888888888888889 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | all | stale | 138 | 9 | 0.2145554347826086956521739130 | 0.2101956797080577384137643043 | -0.004359755074550957238409608639 | -0.02749537374630955 | 0.006147077546234274 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | all | all | 183 | 11 | 0.2203091530054644808743169399 | 0.2170214688508850704978113333 | -0.003287684154579410376505606515 | -0.018974527103024243 | 0.003801963701518486 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | early | fresh | 2421 | 11 | 0.3161248451053283767038413879 | 0.3161248451053283767038413879 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | early | stale | 127 | 2 | 0.2851068897637795275590551181 | 0.2284601754377998535830617590 | -0.05664671432597967397599335960 | -0.09170608487336109 | 0.07320280621987739 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | early | all | 2548 | 11 | 0.3145788167189952904238618524 | 0.3117553737364994432515890281 | -0.002823442982495847172272824438 | -0.009790859553359552 | 0.0023977628220074394 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | middle | fresh | 683 | 10 | 0.2199098096632503660322108346 | 0.2199098096632503660322108346 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | middle | stale | 1726 | 10 | 0.4362076767091541135573580533 | 0.4183323088053429525986803490 | -0.01787536790381116095867770522 | -0.06769100560858395 | 0.0557595021141873 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | middle | all | 2409 | 12 | 0.3748828767123287671232876712 | 0.3620755354910842408407315408 | -0.01280734122124452628255613085 | -0.05210388962469843 | 0.03685882088018021 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | late | fresh | 249 | 8 | 0.01515863453815261044176706827 | 0.01515863453815261044176706827 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | late | stale | 1711 | 10 | 0.3382724722384570426651081239 | 0.1420732285139221164331511773 | -0.1961992437245349262319569469 | -0.31289364617906884 | -0.0813218388462067 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | late | all | 1960 | 12 | 0.2972238265306122448979591837 | 0.1259498948914901740903681961 | -0.1712739316391220708075909879 | -0.27816934965306506 | -0.07107567635536469 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | all | fresh | 3353 | 12 | 0.2741757083209066507605129735 | 0.2741757083209066507605129735 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | all | stale | 3564 | 10 | 0.3838067410213243546576879910 | 0.2789403202205227998898689084 | -0.1048664208008015547678190831 | -0.16387178395157007 | -0.04146164119679512 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | all | all | 6917 | 12 | 0.3306633475495156859910365766 | 0.2766306854511989675881874778 | -0.05403266209831671840284909821 | -0.08818175138029956 | -0.019234538796943385 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | pre_live | all | fresh | 648 | 12 | 0.3036557098765432098765432099 | 0.3036557098765432098765432099 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | pre_live | all | stale | 4271 | 9 | 0.2748771247951299461484429876 | 0.2748771247951299461484429876 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | pre_live | all | all | 4919 | 12 | 0.2786682455783695873144948160 | 0.2786682455783695873144948160 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | early | fresh | 791 | 3 | 0.3584854298356510745891276865 | 0.3584854298356510745891276865 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | early | stale | 41 | 1 | 0.1226786585365853658536585366 | 0.1226786585365853658536585366 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | early | all | 832 | 3 | 0.3468651442307692307692307692 | 0.3468651442307692307692307692 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | middle | fresh | 160 | 3 | 0.3105746875 | 0.3105746875 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | middle | stale | 1104 | 3 | 0.1736364130434782608695652174 | 0.1736364130434782608695652174 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | middle | all | 1264 | 3 | 0.1909703718354430379746835443 | 0.1909703718354430379746835443 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | late | fresh | 8 | 2 | 0.05605000 | 0.05605000 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | late | stale | 803 | 2 | 0.03615202366127023661270236613 | 0.03615202366127023661270236613 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | late | all | 811 | 2 | 0.03634830456226880394574599260 | 0.03634830456226880394574599260 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | all | fresh | 959 | 3 | 0.3479690563086548488008342023 | 0.3479690563086548488008342023 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | all | stale | 1948 | 3 | 0.1158904004106776180698151951 | 0.1158904004106776180698151951 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | all | all | 2907 | 3 | 0.1924516081871345029239766082 | 0.1924516081871345029239766082 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | pre_live | all | fresh | 7 | 2 | 0.4292821428571428571428571429 | 0.4292821428571428571428571429 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | pre_live | all | stale | 8 | 1 | 0.64802500 | 0.64802500 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | pre_live | all | all | 15 | 2 | 0.54594500 | 0.54594500 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | early | fresh | 1359 | 8 | 0.2766198859455481972038263429 | 0.2766198859455481972038263429 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | early | all | 1359 | 8 | 0.2766198859455481972038263429 | 0.2766198859455481972038263429 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | middle | fresh | 1422 | 8 | 0.2001281997187060478199718706 | 0.2001281997187060478199718706 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | middle | stale | 884 | 8 | 0.1950333710407239819004524887 | 0.1950333710407239819004524887 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | middle | all | 2306 | 8 | 0.1981751084128360797918473547 | 0.1981751084128360797918473547 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | late | fresh | 14 | 8 | 0.05489642857142857142857142857 | 0.05489642857142857142857142857 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | late | stale | 1716 | 8 | 0.1677692890442890442890442890 | 0.1677692890442890442890442890 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | late | all | 1730 | 8 | 0.1668558670520231213872832370 | 0.1668558670520231213872832370 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | all | fresh | 2795 | 8 | 0.2365929427549194991055456172 | 0.2365929427549194991055456172 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | all | stale | 2600 | 8 | 0.1770390769230769230769230769 | 0.1770390769230769230769230769 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | all | all | 5395 | 8 | 0.2078922845227062094531974050 | 0.2078922845227062094531974050 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | pre_live | all | fresh | 104 | 8 | 0.3385461538461538461538461538 | 0.3385461538461538461538461538 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | pre_live | all | stale | 4386 | 8 | 0.3245880186958504331965344277 | 0.3245880186958504331965344277 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | pre_live | all | all | 4490 | 8 | 0.3249113251670378619153674833 | 0.3249113251670378619153674833 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |

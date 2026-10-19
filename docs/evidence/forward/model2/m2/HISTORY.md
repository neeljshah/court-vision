# S544 M2 read-out HISTORY (mode: production)

Calibration read-out only: Brier of arm M2 (the landed S542 staleness backstop with frozen constants, nothing fit) and of arm A on identical outcome rows and settlement. Every number is vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's. No statement about the venue.

age = our receipt age (state receipt minus used book receipt), not venue staleness; fresh <= 15 s < stale

prereg seal 936fb8fb6d3d539e978773b8c75be2d6eddfd5b766f3a643287f68b701fd2121; effective date 2026-10-01

## Headline (cumulative class live, segment all, age stale; delta = M2 - A Brier)

| sport | verdict | games | ticks | mean delta | CI lo | CI hi | nights not read out | descriptive | note | label |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mlb | INSUFFICIENT | 10 | 5921 | -0.009731332225819339132916305388 | -0.02850157690278429 | 0.012088190229987235 | 0 | True | MLB is INSUFFICIENT by declaration in this row | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | INSUFFICIENT | 8 | 2676 | -0.1180375266030255975792419321 | -0.17710353213661278 | -0.051361590094972834 | 0 | False | - | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | INSUFFICIENT | 2 | 1134 | 0E-8 | 0.0 | 0.0 | 0 | True | M2 is not defined for this sport (M2 = A) | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | INSUFFICIENT | 5 | 1629 | 0E-8 | 0.0 | 0.0 | 0 | True | M2 is not defined for this sport (M2 = A) | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |

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

## Cumulative cells (non-empty)

| sport | class | segment | age | ticks | games | mean A Brier | mean M2 Brier | mean M2 - A | CI lo | CI hi | label |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mlb | live | early | fresh | 3458 | 10 | 0.3061220864661654135338345865 | 0.3061220864661654135338345865 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | early | stale | 1166 | 10 | 0.2729054245283018867924528302 | 0.2852595900510683633935226671 | 0.01235416552276647660106983653 | -0.004496170527507636 | 0.044061502545244095 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | early | all | 4624 | 10 | 0.2977460856401384083044982699 | 0.3008613445068221694889375915 | 0.003115258866683761184439322965 | -0.0011931914987943638 | 0.011054244580233633 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | middle | fresh | 834 | 10 | 0.2421062949640287769784172662 | 0.2421062949640287769784172662 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | middle | stale | 3093 | 8 | 0.1760201665050113158745554478 | 0.1753805441531498561193066879 | -0.0006396223518614597552487594025 | -0.019068207404248062 | 0.018643073081358513 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | middle | all | 3927 | 10 | 0.1900552648332060096765979119 | 0.1895514828280347606256724181 | -0.0005037820051712490509254934637 | -0.014175151839150323 | 0.015671289725102216 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | late | fresh | 593 | 7 | 0.01446172006745362563237774030 | 0.01446172006745362563237774030 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | late | stale | 1662 | 7 | 0.07892435318892900120336943442 | 0.03677885188067718188937397079 | -0.04214550130825181931399546369 | -0.0923844643708062 | -0.009935199889378606 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | late | all | 2255 | 8 | 0.06197253880266075388026607539 | 0.03091008950141262807101531683 | -0.03106244930124812580925075860 | -0.06944960128041919 | -0.00550010788896916 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | all | fresh | 4885 | 10 | 0.2597876407369498464687819857 | 0.2597876407369498464687819857 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | all | stale | 5921 | 10 | 0.1678450219557507177841580814 | 0.1581136897299313786512417760 | -0.009731332225819339132916305388 | -0.02850157690278429 | 0.012088190229987235 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | live | all | all | 10806 | 10 | 0.2094089394780677401443642421 | 0.2040767889960136676840646445 | -0.005332150482054072460299596909 | -0.016357101951930218 | 0.006343223014437813 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | pre_live | all | fresh | 74 | 7 | 0.3003760135135135135135135135 | 0.3003760135135135135135135135 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | pre_live | all | stale | 3963 | 8 | 0.2798383926318445622003532677 | 0.2798383926318445622003532677 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | pre_live | all | all | 4037 | 8 | 0.2802148563289571463958384939 | 0.2802148563289571463958384939 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | early | fresh | 44 | 2 | 0.2425840909090909090909090909 | 0.2425840909090909090909090909 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | early | stale | 91 | 1 | 0.25502500 | 0.25502500 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | early | all | 135 | 2 | 0.2509701851851851851851851852 | 0.2509701851851851851851851852 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | middle | stale | 12 | 2 | 0.40217500 | 0.3983981747466517199076235176 | -0.0037768252533482800923764821 | -0.2754311555193396 | 0.020919022952650933 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | middle | all | 12 | 2 | 0.40217500 | 0.3983981747466517199076235176 | -0.0037768252533482800923764821 | -0.2754311555193396 | 0.020919022952650933 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | late | stale | 35 | 6 | 0.04500785714285714285714285714 | 0.02911287722148992177737119409 | -0.01589497992136722107977166306 | -0.020905770428357135 | -0.0005710691666039165 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | late | all | 35 | 6 | 0.04500785714285714285714285714 | 0.02911287722148992177737119409 | -0.01589497992136722107977166306 | -0.020905770428357135 | -0.0005710691666039165 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | all | fresh | 44 | 2 | 0.2425840909090909090909090909 | 0.2425840909090909090909090909 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | all | stale | 138 | 9 | 0.2145554347826086956521739130 | 0.2101956797080577384137643043 | -0.004359755074550957238409608639 | -0.02749537374630955 | 0.006147077546234274 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| mlb | terminal | all | all | 182 | 10 | 0.2213315934065934065934065934 | 0.2180258450533624609950520549 | -0.003305748353230945598354538419 | -0.019802779108165934 | 0.0034063255214069115 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | early | fresh | 1762 | 8 | 0.3369989358683314415437003405 | 0.3369989358683314415437003405 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | early | stale | 100 | 1 | 0.21622500 | 0.1245189151266389187095559994 | -0.09170608487336108129044400083 | -0.09170608487336109 | -0.09170608487336109 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | early | all | 1862 | 8 | 0.3305126879699248120300751880 | 0.3255875491475101460101802363 | -0.004925138822414666019894951709 | -0.012910288813706393 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | middle | fresh | 375 | 8 | 0.3167554666666666666666666667 | 0.3167554666666666666666666667 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | middle | stale | 1303 | 8 | 0.4182964504988488104374520338 | 0.3708915885426100781019636814 | -0.04740486195623873233548835355 | -0.08272436581827003 | -0.008248823064490166 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | middle | all | 1678 | 9 | 0.3956040375446960667461263409 | 0.3587932299588920928288788296 | -0.03681080758580397391724751172 | -0.06467295177371514 | -0.005676113193436269 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | late | fresh | 68 | 7 | 0.02017279411764705882352941176 | 0.02017279411764705882352941176 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | late | stale | 1273 | 8 | 0.2932157501963864886095836606 | 0.1008125470751128650747323766 | -0.1924032031212736235348512847 | -0.3316103154798039 | -0.055370688743062654 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | late | all | 1341 | 9 | 0.2793701715137956748695003729 | 0.09672343208547254082038353125 | -0.1826467394283231340491168422 | -0.3167886003496046 | -0.05146050622895571 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | all | fresh | 2205 | 9 | 0.3237855668934240362811791383 | 0.3237855668934240362811791383 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | all | stale | 2676 | 8 | 0.3512430586696562032884902840 | 0.2332055320666306057092483524 | -0.1180375266030255975792419321 | -0.17710353213661278 | -0.051361590094972834 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | live | all | all | 4881 | 9 | 0.3388390903503380454824830977 | 0.2741252159004924197660210176 | -0.06471387444984562571646207955 | -0.10158754662591642 | -0.02632140898059373 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | pre_live | all | fresh | 463 | 9 | 0.3192295356371490280777537797 | 0.3192295356371490280777537797 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | pre_live | all | stale | 2538 | 6 | 0.2291783589440504334121355398 | 0.2291783589440504334121355398 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nba | pre_live | all | all | 3001 | 9 | 0.2430716261246251249583472176 | 0.2430716261246251249583472176 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | early | fresh | 606 | 2 | 0.3770966171617161716171617162 | 0.3770966171617161716171617162 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | early | stale | 41 | 1 | 0.1226786585365853658536585366 | 0.1226786585365853658536585366 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | early | all | 647 | 2 | 0.3609743044822256568778979907 | 0.3609743044822256568778979907 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | middle | fresh | 76 | 2 | 0.5192917763157894736842105263 | 0.5192917763157894736842105263 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | middle | stale | 736 | 2 | 0.2309551630434782608695652174 | 0.2309551630434782608695652174 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | middle | all | 812 | 2 | 0.2579423337438423645320197044 | 0.2579423337438423645320197044 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | late | fresh | 4 | 1 | 0.00062500 | 0.00062500 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | late | stale | 357 | 1 | 0.006764495798319327731092436975 | 0.006764495798319327731092436975 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | late | all | 361 | 1 | 0.006696468144044321329639889197 | 0.006696468144044321329639889197 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | all | fresh | 686 | 2 | 0.3906548469387755102040816327 | 0.3906548469387755102040816327 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | all | stale | 1134 | 2 | 0.1564618606701940035273368607 | 0.1564618606701940035273368607 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | live | all | all | 1820 | 2 | 0.2447346016483516483516483516 | 0.2447346016483516483516483516 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | pre_live | all | fresh | 7 | 2 | 0.4292821428571428571428571429 | 0.4292821428571428571428571429 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | pre_live | all | stale | 8 | 1 | 0.64802500 | 0.64802500 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| nfl | pre_live | all | all | 15 | 2 | 0.54594500 | 0.54594500 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | early | fresh | 853 | 5 | 0.3365445779601406799531066823 | 0.3365445779601406799531066823 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | early | all | 853 | 5 | 0.3365445779601406799531066823 | 0.3365445779601406799531066823 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | middle | fresh | 890 | 5 | 0.2591461797752808988764044944 | 0.2591461797752808988764044944 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | middle | stale | 559 | 5 | 0.2649516547406082289803220036 | 0.2649516547406082289803220036 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | middle | all | 1449 | 5 | 0.2613858350586611456176673568 | 0.2613858350586611456176673568 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | late | fresh | 9 | 5 | 0.08333611111111111111111111111 | 0.08333611111111111111111111111 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | late | stale | 1070 | 5 | 0.2150470560747663551401869159 | 0.2150470560747663551401869159 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | late | all | 1079 | 5 | 0.2139484476367006487488415199 | 0.2139484476367006487488415199 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | all | fresh | 1752 | 5 | 0.2959261700913242009132420091 | 0.2959261700913242009132420091 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | all | stale | 1629 | 5 | 0.2321720841006752608962553714 | 0.2321720841006752608962553714 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | live | all | all | 3381 | 5 | 0.2652088065661047027506654836 | 0.2652088065661047027506654836 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | pre_live | all | fresh | 64 | 5 | 0.44573125 | 0.44573125 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | pre_live | all | stale | 2804 | 5 | 0.4397353423680456490727532097 | 0.4397353423680456490727532097 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
| soccer | pre_live | all | all | 2868 | 5 | 0.4398691422594142259414225941 | 0.4398691422594142259414225941 | 0E-8 | 0.0 | 0.0 | vs our own stale receipt copy of the venue mid; receipt age is ours, not the venue's |
